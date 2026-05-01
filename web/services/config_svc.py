# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json

import constants as C
from db import AppConfig, db

DEFAULT_HALO_COLOR = "#8a2be2"


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


def _default_config():
    return {
        "order": [],
        "durations": {},
        "disabled": [],
        "hidden_recent_jobs": [],
        "groups": {},
        "group_pools": {},
        "group_screens": {},
        "broadcast_links": {},
        "disabled_groups": [],
        "default_screen_name": "",
        "default_halo_color": DEFAULT_HALO_COLOR,
        "screens": {},
        "campaigns": [],
        "client_watchdog": _default_client_watchdog(),
        "activity_log": _default_activity_log(),
        "backup_remote": _default_backup_remote(),
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
    merged["groups"] = cfg.get("groups", {}) if isinstance(cfg.get("groups"), dict) else {}
    merged["group_pools"] = cfg.get("group_pools", {}) if isinstance(cfg.get("group_pools"), dict) else {}
    merged["group_screens"] = cfg.get("group_screens", {}) if isinstance(cfg.get("group_screens"), dict) else {}
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
            base = _default_screen_config(default_halo_color)
            if isinstance(screen_cfg, dict):
                base.update(screen_cfg)
            base["halo_color"] = normalize_halo_color(base.get("halo_color", default_halo_color), default_halo_color)
            normalized_screens[name] = base
    merged["screens"] = normalized_screens
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
    screen = str(screen_name or "").strip().lower()
    if screen:
        scfg = cfg.get("screens", {}).get(screen, {})
        return normalize_halo_color(scfg.get("halo_color", default_halo_color), default_halo_color)
    return default_halo_color


def save_config(cfg):
    normalized = normalize_config(cfg)
    row = db.session.get(AppConfig, 1)
    if row is None:
        db.session.add(AppConfig(id=1, data=json.dumps(normalized)))
    else:
        row.data = json.dumps(normalized)
    db.session.commit()
