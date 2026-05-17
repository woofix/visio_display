# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import logging
import threading
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import constants as C
from flask import has_app_context

from services.activity_svc import log_config_change
from services.backup_svc import copy_backup_to_smb, create_backup_archive
from services.config_svc import load_config, save_config
from services.queue_svc import get_redis


LOGGER = logging.getLogger(__name__)
_flask_app = None
_started = False


def _app_context_for_background_work():
    if has_app_context():
        return nullcontext()
    return _flask_app.app_context()


def _backup_timezone(cfg):
    tz_name = str(cfg.get("meteo_tz") or C.DEFAULT_METEO_TZ).strip() or C.DEFAULT_METEO_TZ
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        LOGGER.warning("Unknown backup scheduler timezone '%s', falling back to %s", tz_name, C.DEFAULT_METEO_TZ)
        return ZoneInfo(C.DEFAULT_METEO_TZ)


def _is_valid_hhmm(value):
    try:
        hour, minute = str(value or "").split(":", 1)
        hour = int(hour)
        minute = int(minute)
    except (TypeError, ValueError):
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59


def get_backup_schedule(cfg=None):
    cfg = cfg or load_config()
    raw = cfg.get("backup_schedule", {})
    if not isinstance(raw, dict):
        raw = {}
    time_value = str(raw.get("time") or "02:00").strip()
    if not _is_valid_hhmm(time_value):
        time_value = "02:00"
    return {
        "enabled": bool(raw.get("enabled", False)),
        "time": time_value,
        "copy_to_smb": bool(raw.get("copy_to_smb", True)),
        "last_run_date": str(raw.get("last_run_date", "") or ""),
        "last_started_at": str(raw.get("last_started_at", "") or ""),
        "last_finished_at": str(raw.get("last_finished_at", "") or ""),
        "last_status": str(raw.get("last_status", "") or ""),
        "last_message": str(raw.get("last_message", "") or ""),
        "last_backup": str(raw.get("last_backup", "") or ""),
    }


def save_backup_schedule(settings):
    cfg = load_config()
    current = get_backup_schedule(cfg)
    time_value = str((settings or {}).get("time") or current["time"]).strip()
    if not _is_valid_hhmm(time_value):
        raise ValueError("invalid backup schedule time")
    cfg["backup_schedule"] = {
        **current,
        "enabled": bool((settings or {}).get("enabled", False)),
        "time": time_value,
        "copy_to_smb": bool((settings or {}).get("copy_to_smb", False)),
    }
    save_config(cfg)
    return cfg["backup_schedule"]


def _mark_schedule_started(cfg, schedule, today_key, now):
    cfg["backup_schedule"] = {
        **schedule,
        "last_run_date": today_key,
        "last_started_at": now.astimezone(timezone.utc).isoformat(),
        "last_finished_at": "",
        "last_status": "running",
        "last_message": "Backup automation started.",
    }
    save_config(cfg)


def _mark_schedule_finished(status, message, backup_filename=""):
    cfg = load_config()
    schedule = get_backup_schedule(cfg)
    cfg["backup_schedule"] = {
        **schedule,
        "last_finished_at": datetime.now(timezone.utc).isoformat(),
        "last_status": status,
        "last_message": str(message or "")[:500],
        "last_backup": backup_filename or schedule.get("last_backup", ""),
    }
    save_config(cfg)


def _run_scheduled_backup():
    cfg = load_config()
    schedule = get_backup_schedule(cfg)
    remote_settings = cfg.get("backup_remote", {})
    backup = create_backup_archive()
    backup_filename = backup["filename"]
    copied = False

    if schedule.get("copy_to_smb"):
        if not remote_settings.get("enabled") or not remote_settings.get("url"):
            raise RuntimeError("Backup created, but SMB copy is enabled without an active SMB destination.")
        copy_backup_to_smb(backup["path"], backup_filename, remote_settings)
        copied = True

    detail = f"scheduled backup created: {backup_filename}"
    if copied:
        detail += " and copied to SMB"
    log_config_change("system", detail)
    _mark_schedule_finished("success", detail, backup_filename)
    LOGGER.info(detail)


def _scheduler_tick():
    with _app_context_for_background_work():
        cfg = load_config()
        schedule = get_backup_schedule(cfg)
        if not schedule["enabled"]:
            return

        now = datetime.now(_backup_timezone(cfg))
        if now.strftime("%H:%M") != schedule["time"]:
            return

        today_key = now.date().isoformat()
        if schedule.get("last_run_date") == today_key:
            return

        lock_key = f"visio-display:backup_scheduler:{today_key}"
        if not get_redis().set(lock_key, 1, nx=True, ex=86400):
            return

        _mark_schedule_started(cfg, schedule, today_key, now)

        try:
            _run_scheduled_backup()
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            log_config_change("system", f"scheduled backup failed: {message}")
            _mark_schedule_finished("error", message)
            LOGGER.exception("Scheduled backup failed")


def _scheduler_loop():
    time.sleep(15)
    while True:
        try:
            _scheduler_tick()
        except Exception:
            LOGGER.exception("Backup scheduler tick failed")
        time.sleep(60)


def start_backup_scheduler_thread(app):
    global _flask_app, _started
    if _started:
        return
    _started = True
    _flask_app = app
    threading.Thread(target=_scheduler_loop, daemon=True).start()
