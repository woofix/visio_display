# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import constants as C
from db import db, ActivityLog
from services.config_svc import load_config


LOGGER = logging.getLogger(__name__)
_last_cleanup_ts = 0.0
_last_vacuum_ts = 0.0


def _get_activity_timezone():
    cfg = load_config()
    tz_name = str(cfg.get('meteo_tz') or C.DEFAULT_METEO_TZ).strip() or C.DEFAULT_METEO_TZ
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        LOGGER.warning("Unknown activity log timezone '%s', falling back to %s", tz_name, C.DEFAULT_METEO_TZ)
        return ZoneInfo(C.DEFAULT_METEO_TZ)


def _format_activity_timestamp(timestamp):
    try:
        utc_dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return timestamp
    return utc_dt.astimezone(_get_activity_timezone()).strftime('%Y-%m-%d %H:%M:%S')


def log_config_change(username, details, *, filename=None):
    log_activity(username, 'config', filename=filename, details=details)


def _trim_activity_log(now_utc):
    deleted = 0
    cutoff = (now_utc - timedelta(days=C.ACTIVITY_LOG_RETENTION_DAYS)).strftime('%Y-%m-%dT%H:%M:%S')
    deleted += (
        ActivityLog.query
        .filter(ActivityLog.timestamp < cutoff)
        .delete(synchronize_session=False)
    )

    remaining = ActivityLog.query.count()
    overflow = remaining - C.ACTIVITY_LOG_MAX_ROWS
    if overflow > 0:
        oldest_ids = [
            row.id
            for row in (
                ActivityLog.query
                .order_by(ActivityLog.id.asc())
                .limit(overflow)
                .all()
            )
        ]
        if oldest_ids:
            deleted += (
                ActivityLog.query
                .filter(ActivityLog.id.in_(oldest_ids))
                .delete(synchronize_session=False)
            )

    if deleted:
        db.session.commit()
    return deleted


def _vacuum_activity_log():
    engine = db.engine
    if engine.dialect.name != 'sqlite':
        return
    conn = None
    try:
        conn = engine.raw_connection()
        conn.execute('VACUUM')
        conn.commit()
    except Exception:
        LOGGER.exception("Unable to compact activity log database")
    finally:
        if conn is not None:
            conn.close()


def _maybe_cleanup_activity_log():
    global _last_cleanup_ts, _last_vacuum_ts

    now = time.monotonic()
    if now - _last_cleanup_ts < C.ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS:
        return

    _last_cleanup_ts = now
    try:
        deleted = _trim_activity_log(datetime.now(timezone.utc))
    except Exception:
        db.session.rollback()
        LOGGER.exception("Unable to prune activity log")
        return

    if deleted and now - _last_vacuum_ts >= C.ACTIVITY_LOG_VACUUM_INTERVAL_SECONDS:
        _last_vacuum_ts = now
        _vacuum_activity_log()


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
        _maybe_cleanup_activity_log()
    except Exception:
        db.session.rollback()
        LOGGER.exception("Unable to write activity log entry")


def get_activity_log(limit=200):
    rows = (ActivityLog.query
            .order_by(ActivityLog.id.desc())
            .limit(limit)
            .all())
    entries = []
    for row in rows:
        entry = row.to_dict()
        entry['timestamp_display'] = _format_activity_timestamp(entry.get('timestamp'))
        entries.append(entry)
    return entries
