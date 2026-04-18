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


def _default_config():
    return {
        "order": [],
        "durations": {},
        "disabled": [],
        "groups": {},
        "disabled_groups": [],
        "screens": {},
        "priority_alert": {
            "message": "",
            "updated_at": None,
        },
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
    merged["disabled_groups"] = cfg.get("disabled_groups", []) if isinstance(cfg.get("disabled_groups"), list) else []
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


def save_config(cfg):
    row = db.session.get(AppConfig, 1)
    if row is None:
        db.session.add(AppConfig(id=1, data=json.dumps(cfg)))
    else:
        row.data = json.dumps(cfg)
    db.session.commit()
