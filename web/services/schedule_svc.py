# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from collections import defaultdict
from datetime import date, datetime, timedelta

from services.media_svc import get_media_groups

GLOBAL_SCOPE = "__global__"


def parse_iso_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def parse_time_to_minutes(value):
    if not value:
        return None
    try:
        hour, minute = map(int, str(value).split(":"))
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def minutes_to_hhmm(minutes):
    minutes = max(0, min(int(minutes), 24 * 60))
    if minutes == 24 * 60:
        return "24:00"
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def start_of_week(day=None):
    day = day or datetime.now().date()
    return day - timedelta(days=day.weekday())


def week_days(week_start):
    return [week_start + timedelta(days=index) for index in range(7)]


def build_schedule_entries(cfg, media_infos, allowed_screens, default_screen_name):
    entries = []
    screen_map = [(GLOBAL_SCOPE, "", default_screen_name, cfg.get("schedules", {}))]
    for screen in allowed_screens:
        schedules = cfg.get("screens", {}).get(screen, {}).get("schedules", {})
        screen_map.append((screen, screen, screen, schedules))

    for scope_key, screen_value, screen_label, schedules in screen_map:
        if not isinstance(schedules, dict):
            continue
        for filename, raw_sched in schedules.items():
            if filename not in media_infos or not isinstance(raw_sched, dict):
                continue
            date_start = str(raw_sched.get("date_start", "")).strip()
            date_end = str(raw_sched.get("date_end", "")).strip()
            time_start = str(raw_sched.get("time_start", "")).strip()
            time_end = str(raw_sched.get("time_end", "")).strip()
            start_minutes = parse_time_to_minutes(time_start)
            end_minutes = parse_time_to_minutes(time_end)
            has_time = start_minutes is not None or end_minutes is not None
            entry = {
                "id": f"{scope_key}::{filename}",
                "scope_key": scope_key,
                "screen": screen_value,
                "screen_label": screen_label,
                "filename": filename,
                "groups": get_media_groups(filename, cfg),
                "type": media_infos.get(filename, {}).get("type", "unknown"),
                "size": media_infos.get(filename, {}).get("size", "--"),
                "dims": media_infos.get(filename, {}).get("dims", "--"),
                "date_start": date_start,
                "date_end": date_end,
                "time_start": time_start,
                "time_end": time_end,
                "date_start_obj": parse_iso_date(date_start),
                "date_end_obj": parse_iso_date(date_end),
                "start_minutes": 0 if start_minutes is None else start_minutes,
                "end_minutes": (24 * 60) if end_minutes is None else end_minutes,
                "has_time": has_time,
                "is_all_day": not has_time,
            }
            entries.append(entry)

    entries.sort(
        key=lambda item: (
            item["screen_label"].casefold(),
            item["date_start"] or "0000-00-00",
            item["time_start"] or "00:00",
            item["filename"].casefold(),
        )
    )
    return entries


def schedule_summary(entry, translate=None):
    translate = translate or (lambda key, **kwargs: key)
    parts = []
    if entry.get("has_time"):
        parts.append(f'{entry.get("time_start") or "00:00"} - {entry.get("time_end") or "24:00"}')
    else:
        parts.append(translate("programming_all_day"))
    if entry.get("date_start") or entry.get("date_end"):
        parts.append(f'{entry.get("date_start") or "..." } -> {entry.get("date_end") or "..."}')
    else:
        parts.append(translate("programming_no_date_limit"))
    return " · ".join(parts)


def entry_matches_date(entry, day):
    date_start = entry.get("date_start_obj")
    date_end = entry.get("date_end_obj")
    if date_start and day < date_start:
        return False
    if date_end and day > date_end:
        return False
    return True


def expand_entry_for_week(entry, week_start):
    occurrences = []
    for day in week_days(week_start):
        if not entry_matches_date(entry, day):
            continue
        occurrences.append({
            "entry_id": entry["id"],
            "filename": entry["filename"],
            "screen_label": entry["screen_label"],
            "screen": entry["screen"],
            "day": day,
            "day_iso": day.isoformat(),
            "start_minutes": entry["start_minutes"],
            "end_minutes": entry["end_minutes"],
            "is_all_day": entry["is_all_day"],
            "groups": entry["groups"],
        })
    return occurrences


def analyze_schedule_week(entries, week_start):
    occurrences = defaultdict(list)
    entry_issue_counts = defaultdict(lambda: {"overlaps": 0, "gaps": 0})
    scope_labels = {}

    for entry in entries:
        scope_labels[entry["scope_key"]] = entry["screen_label"]
        for occurrence in expand_entry_for_week(entry, week_start):
            occurrences[(entry["scope_key"], occurrence["day_iso"])].append(occurrence)

    calendar_rows = []
    for scope_key, screen_label in sorted(scope_labels.items(), key=lambda item: item[1].casefold()):
        cells = []
        row_overlap_count = 0
        row_gap_count = 0
        for day in week_days(week_start):
            day_iso = day.isoformat()
            items = sorted(
                occurrences.get((scope_key, day_iso), []),
                key=lambda item: (item["start_minutes"], item["end_minutes"], item["filename"].casefold()),
            )
            overlaps = []
            gaps = []

            if items:
                prev = items[0]
                max_end = prev["end_minutes"]
                for current in items[1:]:
                    if current["start_minutes"] < max_end:
                        overlap_end = min(max_end, current["end_minutes"])
                        overlaps.append({
                            "start": current["start_minutes"],
                            "end": overlap_end,
                            "label": f'{minutes_to_hhmm(current["start_minutes"])} - {minutes_to_hhmm(overlap_end)}',
                            "filenames": [prev["filename"], current["filename"]],
                        })
                        entry_issue_counts[prev["entry_id"]]["overlaps"] += 1
                        entry_issue_counts[current["entry_id"]]["overlaps"] += 1
                    elif current["start_minutes"] > prev["end_minutes"]:
                        gaps.append({
                            "start": prev["end_minutes"],
                            "end": current["start_minutes"],
                            "label": (
                                f'{minutes_to_hhmm(prev["end_minutes"])} - '
                                f'{minutes_to_hhmm(current["start_minutes"])}'
                            ),
                        })
                    if current["end_minutes"] >= max_end:
                        prev = current
                        max_end = current["end_minutes"]

            row_overlap_count += len(overlaps)
            row_gap_count += len(gaps)
            cells.append({
                "day_iso": day_iso,
                "items": items,
                "overlaps": overlaps,
                "gaps": gaps,
            })

        calendar_rows.append({
            "scope_key": scope_key,
            "screen_label": screen_label,
            "cells": cells,
            "overlap_count": row_overlap_count,
            "gap_count": row_gap_count,
        })

    return {
        "calendar_rows": calendar_rows,
        "entry_issue_counts": dict(entry_issue_counts),
    }
