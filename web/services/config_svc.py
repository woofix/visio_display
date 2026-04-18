import json
from db import db, AppConfig


def load_config():
    row = db.session.get(AppConfig, 1)
    if row is None:
        return {"order": [], "durations": {}, "disabled": []}
    try:
        return json.loads(row.data)
    except Exception:
        return {"order": [], "durations": {}, "disabled": []}


def save_config(cfg):
    row = db.session.get(AppConfig, 1)
    if row is None:
        db.session.add(AppConfig(id=1, data=json.dumps(cfg)))
    else:
        row.data = json.dumps(cfg)
    db.session.commit()
