# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import hashlib
import os
from datetime import date, datetime

from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.config_svc import get_default_screen_name, get_screen_keys, load_config
from services.media_svc import get_all_media, get_file_info, get_media_groups, get_media_type


LARGE_VIDEO_THRESHOLD_BYTES = 250 * 1024 * 1024
DISABLED_OLD_DAYS = 90


def _file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _size_label(size_bytes):
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} Go"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} Mo"
    return f"{max(1, round(size_bytes / 1024))} Ko"


def _age_days(timestamp, now):
    return max(0, int((now - datetime.fromtimestamp(timestamp)).total_seconds() // 86400))


def _parse_date(value):
    try:
        return date.fromisoformat(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def _screen_label(screen, cfg=None):
    return screen or get_default_screen_name(cfg) or "global"


def _media_entry(filename, now):
    path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        stat = os.stat(path)
    except OSError:
        return None
    info = get_file_info(filename, include_dimensions=False)
    return {
        "filename": filename,
        "type": get_media_type(filename),
        "size_bytes": stat.st_size,
        "size_label": _size_label(stat.st_size),
        "age_days": _age_days(stat.st_mtime, now),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="minutes"),
        "info": info,
    }


def _iter_schedule_refs(cfg):
    for filename, sched in cfg.get("schedules", {}).items():
        if isinstance(sched, dict):
            yield "", filename, sched
    for screen, screen_cfg in cfg.get("screens", {}).items():
        if not isinstance(screen_cfg, dict):
            continue
        for filename, sched in screen_cfg.get("schedules", {}).items():
            if isinstance(sched, dict):
                yield screen, filename, sched


def _collect_references(cfg, available_files=None):
    references = {}
    available_files = set(available_files or [])

    def add(filename, label):
        references.setdefault(filename, set()).add(label)

    for filename in cfg.get("order", []):
        if filename in available_files:
            add(filename, "global")

    for screen, screen_cfg in cfg.get("screens", {}).items():
        if not isinstance(screen_cfg, dict):
            continue
        for filename in screen_cfg.get("order", []):
            if filename in available_files:
                add(filename, f"screen:{screen}")

    for campaign in cfg.get("campaigns", []):
        if not isinstance(campaign, dict) or campaign.get("archived"):
            continue
        name = campaign.get("name") or campaign.get("id") or "campaign"
        for filename in campaign.get("media", []):
            add(filename, f"campaign:{name}")
        for filename in _campaign_group_media(campaign, cfg, available_files):
            add(filename, f"campaign:{name}")

    for _screen, filename, _sched in _iter_schedule_refs(cfg):
        add(filename, "schedule")

    return references


def _campaign_group_media(campaign, cfg, available_files):
    if not campaign.get("groups"):
        return set()

    from services.campaign_svc import campaign_target_media

    screens = campaign.get("screens", [])
    if screens:
        target_screens = screens
    else:
        target_screens = get_screen_keys(cfg)

    filenames = set()
    for screen in target_screens:
        filenames.update(
            campaign_target_media(
                campaign,
                cfg,
                screen=screen,
                available_files=available_files,
            )
        )
    return filenames


def _collect_disabled(cfg):
    disabled = {}
    for filename in cfg.get("disabled", []):
        disabled.setdefault(filename, set()).add("global")
    for screen, screen_cfg in cfg.get("screens", {}).items():
        if not isinstance(screen_cfg, dict):
            continue
        for filename in screen_cfg.get("disabled", []):
            disabled.setdefault(filename, set()).add(f"screen:{screen}")
    return disabled


def analyze_media_cleanup(cfg=None, now=None):
    cfg = cfg or load_config()
    now = now or datetime.now()
    today = now.date()
    files = get_all_media(cfg)
    file_set = set(files)
    entries = {
        filename: _media_entry(filename, now)
        for filename in files
    }
    entries = {filename: entry for filename, entry in entries.items() if entry}

    references = _collect_references(cfg, file_set)
    disabled = _collect_disabled(cfg)

    expired = []
    for screen, filename, sched in _iter_schedule_refs(cfg):
        if filename not in file_set:
            continue
        end_date = _parse_date(sched.get("date_end"))
        if end_date and end_date < today:
            expired.append({
                **entries[filename],
                "screen": _screen_label(screen, cfg),
                "reason": end_date.isoformat(),
            })

    unused = []
    for filename in files:
        if references.get(filename):
            continue
        unused.append({
            **entries[filename],
            "groups": get_media_groups(filename, cfg),
        })

    large_videos = [
        {
            **entries[filename],
            "reason": _size_label(entries[filename]["size_bytes"]),
        }
        for filename in files
        if os.path.splitext(filename)[1].lower() in VIDEO_EXTS
        and entries[filename]["size_bytes"] >= LARGE_VIDEO_THRESHOLD_BYTES
    ]

    disabled_old = [
        {
            **entries[filename],
            "scopes": sorted(scopes),
            "reason": str(entries[filename]["age_days"]),
        }
        for filename, scopes in disabled.items()
        if filename in entries and entries[filename]["age_days"] >= DISABLED_OLD_DAYS
    ]

    by_size = {}
    for filename in files:
        size = entries[filename]["size_bytes"]
        if size > 0:
            by_size.setdefault(size, []).append(filename)

    duplicate_groups = []
    for same_size_files in by_size.values():
        if len(same_size_files) < 2:
            continue
        by_hash = {}
        for filename in same_size_files:
            path = os.path.join(UPLOAD_FOLDER, filename)
            try:
                digest = _file_hash(path)
            except OSError:
                continue
            by_hash.setdefault(digest, []).append(filename)
        for digest, hashed_files in by_hash.items():
            if len(hashed_files) < 2:
                continue
            duplicate_groups.append({
                "hash": digest[:12],
                "size_label": entries[hashed_files[0]]["size_label"],
                "files": [entries[filename] for filename in sorted(hashed_files, key=str.casefold)],
            })

    expired.sort(key=lambda item: (item["reason"], item["filename"].casefold()))
    unused.sort(key=lambda item: item["filename"].casefold())
    large_videos.sort(key=lambda item: (-item["size_bytes"], item["filename"].casefold()))
    disabled_old.sort(key=lambda item: (-item["age_days"], item["filename"].casefold()))
    duplicate_groups.sort(key=lambda item: (-len(item["files"]), item["files"][0]["filename"].casefold()))

    categories = {
        "expired": expired,
        "unused": unused,
        "duplicates": duplicate_groups,
        "large_videos": large_videos,
        "disabled_old": disabled_old,
    }

    recoverable_bytes = sum(item["size_bytes"] for item in unused)
    recoverable_bytes += sum(item["size_bytes"] for item in large_videos)
    recoverable_bytes += sum(
        sum(file_item["size_bytes"] for file_item in group["files"][1:])
        for group in duplicate_groups
    )

    return {
        "generated_at": now.isoformat(timespec="minutes"),
        "thresholds": {
            "large_video_bytes": LARGE_VIDEO_THRESHOLD_BYTES,
            "disabled_old_days": DISABLED_OLD_DAYS,
        },
        "categories": categories,
        "summary": {
            "media_count": len(files),
            "expired_count": len(expired),
            "unused_count": len(unused),
            "duplicate_group_count": len(duplicate_groups),
            "large_video_count": len(large_videos),
            "disabled_old_count": len(disabled_old),
            "recoverable_label": _size_label(recoverable_bytes) if recoverable_bytes else "0 Ko",
        },
    }
