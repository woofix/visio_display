# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import re

import constants as C
from db import AppConfig, db

DEFAULT_HALO_COLOR = "#8a2be2"
DEFAULT_SCREEN_KEY = ""
CONFIG_REVISION_KEY = "_config_revision"


def normalize_default_screen_name(value):
    cleaned = " ".join(str(value or "").split())
    return cleaned[:48]


def normalize_halo_color(value, fallback=DEFAULT_HALO_COLOR):
    raw = str(value or "").strip().lower()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 3 and all(ch in "0123456789abcdef" for ch in raw):
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) == 6 and all(ch in "0123456789abcdef" for ch in raw):
        return f"#{raw}"
    return fallback


def halo_color_to_rgb(color):
    normalized = normalize_halo_color(color)
    return ", ".join(str(int(normalized[idx:idx + 2], 16)) for idx in (1, 3, 5))


def get_default_screen_name(cfg=None):
    cfg = cfg or load_config()
    custom_name = normalize_default_screen_name(cfg.get("default_screen_name", ""))
    return custom_name or None


def get_default_screen_key(cfg=None):
    return normalize_screen_name(get_default_screen_name(cfg) or "")


def normalize_screen_name(value):
    screen = str(value or "").strip().lower()
    screen = re.sub(r"\s+", "_", screen)
    screen = "".join(ch for ch in screen if ch.isalnum() or ch in ("_", "-"))
    return screen[:32]


def is_default_screen(screen_name, cfg=None):
    screen = str(screen_name or "").strip().lower()
    return screen == DEFAULT_SCREEN_KEY or bool(get_default_screen_key(cfg)) and screen == get_default_screen_key(cfg)


def normalize_screen_key(screen_name, cfg=None):
    screen = normalize_screen_name(screen_name)
    if screen == DEFAULT_SCREEN_KEY:
        default_key = get_default_screen_key(cfg)
        screens = (cfg or {}).get("screens", {}) if isinstance(cfg, dict) else {}
        return default_key if default_key and default_key in screens else DEFAULT_SCREEN_KEY
    return screen


def screen_exists(cfg, screen_name):
    screen = normalize_screen_key(screen_name, cfg)
    return screen == DEFAULT_SCREEN_KEY or screen in cfg.get("screens", {})


def get_screen_config(cfg, screen_name):
    screen = normalize_screen_key(screen_name, cfg)
    if screen == DEFAULT_SCREEN_KEY:
        return cfg
    return cfg.get("screens", {}).get(screen)


def get_screen_keys(cfg, *, include_default=True):
    screens = cfg.get("screens", {})
    keys = []
    if include_default:
        default_key = normalize_screen_key(DEFAULT_SCREEN_KEY, cfg)
        keys.append(default_key)
    keys.extend(screen for screen in screens.keys() if screen not in keys)
    return keys


def _replace_screen_refs(value, replacements):
    if not replacements:
        return value
    if isinstance(value, list):
        updated = []
        seen = set()
        for item in value:
            key = str(item)
            replacement = replacements.get(key, replacements.get(normalize_screen_name(key), key))
            if replacement not in seen:
                updated.append(replacement)
                seen.add(replacement)
        return updated
    if isinstance(value, dict):
        updated = {}
        for key, item in value.items():
            replacement_key = replacements.get(str(key), replacements.get(normalize_screen_name(key), str(key)))
            if isinstance(item, list):
                item = _replace_screen_refs(item, replacements)
            if replacement_key in updated and isinstance(updated[replacement_key], list) and isinstance(item, list):
                updated[replacement_key] = _replace_screen_refs(updated[replacement_key] + item, {})
            else:
                updated[replacement_key] = item
        return updated
    return value


def _default_screen_config(halo_color=DEFAULT_HALO_COLOR):
    return {
        "order": [],
        "disabled": [],
        "disabled_groups": [],
        "durations": {},
        "schedules": {},
        "halo_color": normalize_halo_color(halo_color),
    }


def _default_features():
    return {
        "upload":         True,
        "announcements":  True,
        "menus":          True,
        "videos":         True,
        "delete":         True,
        "compress":       True,
        "ephemeris":      True,
        "schedule":       True,
        "groups":         True,
        "screens":        True,
        "priority_alert": True,
        "activity":       True,
    }


def _default_client_watchdog():
    return {
        "check_interval_seconds": 30,
        "grace_period_seconds": 90,
        "consecutive_failures_before_reboot": 1,
    }


def _default_activity_log():
    return {
        "auto_delete_enabled": True,
        "retention_days": C.ACTIVITY_LOG_RETENTION_DAYS,
        "max_rows": C.ACTIVITY_LOG_MAX_ROWS,
    }


def _default_backup_remote():
    return {
        "enabled": False,
        "url": "",
        "username": "",
        "password": "",
    }


def _default_backup_schedule():
    return {
        "enabled": False,
        "time": "02:00",
        "copy_to_smb": True,
        "last_run_date": "",
        "last_started_at": "",
        "last_finished_at": "",
        "last_status": "",
        "last_message": "",
        "last_backup": "",
    }


def _default_backup_retention():
    return {
        "max_versions": 5,
    }


def _default_config():
    return {
        CONFIG_REVISION_KEY: 0,
        "order": [],
        "durations": {},
        "disabled": [],
        "hidden_recent_jobs": [],
        "groups": {},
        "group_pools": {},
        "group_screens": {},
        "generated_menus": {},
        "broadcast_links": {},
        "disabled_groups": [],
        "default_screen_name": "",
        "default_halo_color": DEFAULT_HALO_COLOR,
        "screens": {},
        "campaigns": [],
        "client_watchdog": _default_client_watchdog(),
        "activity_log": _default_activity_log(),
        "backup_remote": _default_backup_remote(),
        "backup_schedule": _default_backup_schedule(),
        "backup_retention": _default_backup_retention(),
        "priority_alert": {
            "message": "",
            "updated_at": None,
        },
        "features": _default_features(),
    }


def normalize_config(cfg):
    if not isinstance(cfg, dict):
        cfg = {}
    merged = _default_config()
    merged.update(cfg)
    try:
        merged[CONFIG_REVISION_KEY] = max(0, int(cfg.get(CONFIG_REVISION_KEY, 0) or 0))
    except (TypeError, ValueError):
        merged[CONFIG_REVISION_KEY] = 0
    merged["groups"] = cfg.get("groups", {}) if isinstance(cfg.get("groups"), dict) else {}
    merged["group_pools"] = cfg.get("group_pools", {}) if isinstance(cfg.get("group_pools"), dict) else {}
    merged["group_screens"] = cfg.get("group_screens", {}) if isinstance(cfg.get("group_screens"), dict) else {}
    merged["generated_menus"] = cfg.get("generated_menus", {}) if isinstance(cfg.get("generated_menus"), dict) else {}
    raw_bl = cfg.get("broadcast_links", {})
    merged["broadcast_links"] = {
        str(k): [str(t) for t in v] if isinstance(v, list) else []
        for k, v in raw_bl.items()
    } if isinstance(raw_bl, dict) else {}
    merged["campaigns"] = cfg.get("campaigns", []) if isinstance(cfg.get("campaigns"), list) else []
    merged["hidden_recent_jobs"] = [
        str(job_id) for job_id in cfg.get("hidden_recent_jobs", [])
        if str(job_id).strip()
    ] if isinstance(cfg.get("hidden_recent_jobs"), list) else []
    merged["disabled_groups"] = cfg.get("disabled_groups", []) if isinstance(cfg.get("disabled_groups"), list) else []
    merged["default_screen_name"] = normalize_default_screen_name(cfg.get("default_screen_name", ""))
    merged["default_halo_color"] = normalize_halo_color(cfg.get("default_halo_color", DEFAULT_HALO_COLOR))
    default_halo_color = merged["default_halo_color"]
    stored_features = cfg.get("features", {})
    merged["features"] = {**_default_features(), **(stored_features if isinstance(stored_features, dict) else {})}
    stored_watchdog = cfg.get("client_watchdog", {})
    merged["client_watchdog"] = {
        **_default_client_watchdog(),
        **(stored_watchdog if isinstance(stored_watchdog, dict) else {}),
    }
    stored_activity_log = cfg.get("activity_log", {})
    merged["activity_log"] = {
        **_default_activity_log(),
        **(stored_activity_log if isinstance(stored_activity_log, dict) else {}),
    }
    stored_backup_remote = cfg.get("backup_remote", {})
    merged["backup_remote"] = {
        **_default_backup_remote(),
        **(stored_backup_remote if isinstance(stored_backup_remote, dict) else {}),
    }
    merged["backup_remote"]["enabled"] = bool(merged["backup_remote"].get("enabled", False))
    for key in ("url", "username", "password"):
        merged["backup_remote"][key] = str(merged["backup_remote"].get(key, "") or "").strip()
    stored_backup_schedule = cfg.get("backup_schedule", {})
    merged["backup_schedule"] = {
        **_default_backup_schedule(),
        **(stored_backup_schedule if isinstance(stored_backup_schedule, dict) else {}),
    }
    merged["backup_schedule"]["enabled"] = bool(merged["backup_schedule"].get("enabled", False))
    merged["backup_schedule"]["copy_to_smb"] = bool(merged["backup_schedule"].get("copy_to_smb", True))
    for key in ("time", "last_run_date", "last_started_at", "last_finished_at", "last_status", "last_message", "last_backup"):
        merged["backup_schedule"][key] = str(merged["backup_schedule"].get(key, "") or "").strip()
    stored_backup_retention = cfg.get("backup_retention", {})
    merged["backup_retention"] = {
        **_default_backup_retention(),
        **(stored_backup_retention if isinstance(stored_backup_retention, dict) else {}),
    }
    try:
        merged["backup_retention"]["max_versions"] = min(
            365,
            max(1, int(merged["backup_retention"].get("max_versions"))),
        )
    except (TypeError, ValueError):
        merged["backup_retention"]["max_versions"] = _default_backup_retention()["max_versions"]
    for key, minimum in (
        ("check_interval_seconds", 15),
        ("grace_period_seconds", 30),
        ("consecutive_failures_before_reboot", 1),
    ):
        try:
            merged["client_watchdog"][key] = max(minimum, int(merged["client_watchdog"].get(key)))
        except (TypeError, ValueError):
            merged["client_watchdog"][key] = _default_client_watchdog()[key]
    merged["activity_log"]["auto_delete_enabled"] = bool(
        merged["activity_log"].get("auto_delete_enabled", True)
    )
    max_rows_minimum = min(1000, C.ACTIVITY_LOG_MAX_ROWS)
    for key, minimum, fallback in (
        ("retention_days", 1, _default_activity_log()["retention_days"]),
        ("max_rows", max_rows_minimum, _default_activity_log()["max_rows"]),
    ):
        try:
            merged["activity_log"][key] = max(minimum, int(merged["activity_log"].get(key)))
        except (TypeError, ValueError):
            merged["activity_log"][key] = fallback
    screens = cfg.get("screens", {})
    normalized_screens = {}
    if isinstance(screens, dict):
        for name, screen_cfg in screens.items():
            screen_key = normalize_screen_name(name)
            if not screen_key:
                continue
            base = _default_screen_config(default_halo_color)
            if isinstance(screen_cfg, dict):
                base.update(screen_cfg)
            base["halo_color"] = normalize_halo_color(base.get("halo_color", default_halo_color), default_halo_color)
            if screen_key in normalized_screens:
                existing = normalized_screens[screen_key]
                for list_key in ("order", "disabled", "disabled_groups"):
                    existing[list_key] = _replace_screen_refs(existing.get(list_key, []) + base.get(list_key, []), {})
                for dict_key in ("durations", "schedules"):
                    existing.setdefault(dict_key, {}).update(base.get(dict_key, {}))
                existing["halo_color"] = base.get("halo_color", existing.get("halo_color", default_halo_color))
            else:
                normalized_screens[screen_key] = base
    default_screen_key = get_default_screen_key(merged)
    replacements = {
        str(name): normalize_screen_name(name)
        for name in (screens.keys() if isinstance(screens, dict) else [])
        if normalize_screen_name(name)
    }
    if default_screen_key:
        legacy_default = _default_screen_config(default_halo_color)
        for key in ("order", "disabled", "disabled_groups", "durations", "schedules"):
            legacy_default[key] = merged.get(key, legacy_default[key])
        legacy_default["halo_color"] = normalize_halo_color(
            merged.get("default_halo_color", default_halo_color),
            default_halo_color,
        )
        if default_screen_key not in normalized_screens:
            normalized_screens[default_screen_key] = legacy_default
        else:
            target = normalized_screens[default_screen_key]
            if not target.get("order") and legacy_default.get("order"):
                target["order"] = list(legacy_default["order"])
            if not target.get("disabled") and legacy_default.get("disabled"):
                target["disabled"] = list(legacy_default["disabled"])
            if not target.get("disabled_groups") and legacy_default.get("disabled_groups"):
                target["disabled_groups"] = list(legacy_default["disabled_groups"])
            if not target.get("durations") and legacy_default.get("durations"):
                target["durations"] = dict(legacy_default["durations"])
            if not target.get("schedules") and legacy_default.get("schedules"):
                target["schedules"] = dict(legacy_default["schedules"])
        replacements[DEFAULT_SCREEN_KEY] = default_screen_key
    merged["screens"] = normalized_screens
    if replacements:
        merged["group_screens"] = {
            group: _replace_screen_refs(screens, replacements)
            for group, screens in merged.get("group_screens", {}).items()
        }
        merged["broadcast_links"] = _replace_screen_refs(merged.get("broadcast_links", {}), replacements)
        migrated_campaigns = []
        for campaign in merged.get("campaigns", []):
            if isinstance(campaign, dict):
                campaign = dict(campaign)
                campaign["screens"] = _replace_screen_refs(campaign.get("screens", []), replacements)
            migrated_campaigns.append(campaign)
        merged["campaigns"] = migrated_campaigns
    alert = cfg.get('priority_alert', {})
    if not isinstance(alert, dict):
        alert = {}
    merged['priority_alert'] = {
        'message': str(alert.get('message', '') or ''),
        'updated_at': alert.get('updated_at'),
    }
    return merged


def load_config():
    row = db.session.get(AppConfig, 1)
    if row is None:
        return _default_config()
    try:
        cfg = json.loads(row.data)
    except json.JSONDecodeError:
        return _default_config()
    return normalize_config(cfg)


def is_feature_enabled(feature_name):
    cfg = load_config()
    return bool(cfg.get("features", {}).get(feature_name, True))


def get_screen_halo_color(screen_name="", cfg=None):
    cfg = cfg or load_config()
    default_halo_color = normalize_halo_color(cfg.get("default_halo_color", DEFAULT_HALO_COLOR))
    screen = normalize_screen_key(screen_name, cfg)
    if screen:
        scfg = cfg.get("screens", {}).get(screen, {})
        return normalize_halo_color(scfg.get("halo_color", default_halo_color), default_halo_color)
    return default_halo_color


def save_config(cfg):
    normalized = normalize_config(cfg)
    row = db.session.get(AppConfig, 1)
    current_revision = 0
    if row is not None:
        try:
            current_data = json.loads(row.data)
            current_revision = int(current_data.get(CONFIG_REVISION_KEY, 0) or 0)
        except (TypeError, ValueError, json.JSONDecodeError):
            current_revision = 0
    normalized[CONFIG_REVISION_KEY] = current_revision + 1
    if row is None:
        db.session.add(AppConfig(id=1, data=json.dumps(normalized)))
    else:
        row.data = json.dumps(normalized)
    db.session.commit()
