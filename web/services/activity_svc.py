from datetime import datetime, timezone

from db import db, ActivityLog


def log_activity(username, action, filename=None, details=None):
    try:
        entry = ActivityLog(
            timestamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'),
            username=username or 'system',
            action=action,
            filename=filename,
            details=details,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_activity_log(limit=200):
    rows = (ActivityLog.query
            .order_by(ActivityLog.id.desc())
            .limit(limit)
            .all())
    return [r.to_dict() for r in rows]
