import json
from db import db, AppConfig


def _default_screen_config():
    return {
        "order": [],
        "disabled": [],
        "disabled_groups": [],
        "durations": {},
        "schedules": {},
    }


def _default_features():
    return {
        "upload":         True,
        "delete":         True,
        "compress":       True,
        "ephemeris":      True,
        "schedule":       True,
        "groups":         True,
        "screens":        True,
        "priority_alert": True,
        "activity":       True,
    }


def _default_config():
    return {
        "order": [],
        "durations": {},
        "disabled": [],
        "groups": {},
        "group_pools": {},
        "group_screens": {},
        "disabled_groups": [],
        "screens": {},
        "priority_alert": {
            "message": "",
            "updated_at": None,
        },
        "features": _default_features(),
    }


def load_config():
    row = db.session.get(AppConfig, 1)
    if row is None:
        return _default_config()
    try:
        cfg = json.loads(row.data)
    except Exception:
        return _default_config()
    if not isinstance(cfg, dict):
        return _default_config()
    merged = _default_config()
    merged.update(cfg)
    merged["groups"] = cfg.get("groups", {}) if isinstance(cfg.get("groups"), dict) else {}
    merged["group_pools"] = cfg.get("group_pools", {}) if isinstance(cfg.get("group_pools"), dict) else {}
    merged["group_screens"] = cfg.get("group_screens", {}) if isinstance(cfg.get("group_screens"), dict) else {}
    merged["disabled_groups"] = cfg.get("disabled_groups", []) if isinstance(cfg.get("disabled_groups"), list) else []
    stored_features = cfg.get("features", {})
    merged["features"] = {**_default_features(), **(stored_features if isinstance(stored_features, dict) else {})}
    screens = cfg.get("screens", {})
    normalized_screens = {}
    if isinstance(screens, dict):
        for name, screen_cfg in screens.items():
            base = _default_screen_config()
            if isinstance(screen_cfg, dict):
                base.update(screen_cfg)
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


def is_feature_enabled(feature_name):
    cfg = load_config()
    return bool(cfg.get("features", {}).get(feature_name, True))


def save_config(cfg):
    row = db.session.get(AppConfig, 1)
    if row is None:
        db.session.add(AppConfig(id=1, data=json.dumps(cfg)))
    else:
        row.data = json.dumps(cfg)
    db.session.commit()
