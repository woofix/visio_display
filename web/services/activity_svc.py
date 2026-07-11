# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

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


def _normalize_activity_settings(raw_settings):
    if not isinstance(raw_settings, dict):
        raw_settings = {}

    try:
        retention_days = max(1, int(raw_settings.get('retention_days', C.ACTIVITY_LOG_RETENTION_DAYS)))
    except (TypeError, ValueError):
        retention_days = C.ACTIVITY_LOG_RETENTION_DAYS

    try:
        max_rows = max(1000, int(raw_settings.get('max_rows', C.ACTIVITY_LOG_MAX_ROWS)))
    except (TypeError, ValueError):
        max_rows = C.ACTIVITY_LOG_MAX_ROWS

    return {
        'auto_delete_enabled': bool(raw_settings.get('auto_delete_enabled', True)),
        'retention_days': retention_days,
        'max_rows': max_rows,
    }


def get_activity_settings(cfg=None):
    cfg = cfg or load_config()
    return _normalize_activity_settings(cfg.get('activity_log'))


def log_config_change(username, details, *, filename=None):
    log_activity(username, 'config', filename=filename, details=details)


def _trim_activity_log(now_utc, settings=None):
    settings = settings or get_activity_settings()
    deleted = 0
    if settings.get('auto_delete_enabled', True):
        cutoff = (now_utc - timedelta(days=settings['retention_days'])).strftime('%Y-%m-%dT%H:%M:%S')
        deleted += (
            ActivityLog.query
            .filter(ActivityLog.timestamp < cutoff)
            .delete(synchronize_session=False)
        )

    remaining = ActivityLog.query.count()
    overflow = remaining - settings['max_rows']
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


def get_activity_summary():
    total_entries = ActivityLog.query.count()
    oldest = ActivityLog.query.order_by(ActivityLog.id.asc()).first()
    newest = ActivityLog.query.order_by(ActivityLog.id.desc()).first()
    user_count = db.session.query(ActivityLog.username).distinct().count()
    settings = get_activity_settings()
    return {
        'total_entries': total_entries,
        'user_count': user_count,
        'oldest_timestamp_display': _format_activity_timestamp(oldest.timestamp) if oldest else None,
        'newest_timestamp_display': _format_activity_timestamp(newest.timestamp) if newest else None,
        'settings': settings,
    }


def apply_activity_retention_now():
    try:
        deleted = _trim_activity_log(datetime.now(timezone.utc), settings=get_activity_settings())
    except Exception:
        db.session.rollback()
        LOGGER.exception("Unable to apply activity retention immediately")
        return 0
    return deleted


def purge_activity_log(*, older_than_days=None):
    query = ActivityLog.query
    if older_than_days is not None:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(1, int(older_than_days)))
        ).strftime('%Y-%m-%dT%H:%M:%S')
        query = query.filter(ActivityLog.timestamp < cutoff)
    deleted = query.delete(synchronize_session=False)
    db.session.commit()
    return deleted
