# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import time
import uuid
from contextlib import contextmanager

from constants import PRIVATE_DATA_DIR


LOCK_FILE = os.path.join(PRIVATE_DATA_DIR, "system_task.lock")
DEFAULT_TIMEOUT_SECONDS = 30 * 60
RESTART_TIMEOUT_SECONDS = 10 * 60


class SystemTaskAlreadyRunning(RuntimeError):
    pass


def _now():
    return time.time()


def _iso(timestamp):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _timeout_for(task_type, timeout_seconds=None):
    if timeout_seconds is not None:
        return max(30, int(timeout_seconds))
    return RESTART_TIMEOUT_SECONDS if task_type == "reboot" else DEFAULT_TIMEOUT_SECONDS


def _public_status(lock_data):
    if not lock_data:
        return {
            "active": False,
            "task": None,
            "type": None,
            "message": "",
            "progress": None,
        }
    task = {
        "type": lock_data.get("type"),
        "message": lock_data.get("message") or "Opération système en cours...",
        "progress": lock_data.get("progress"),
        "started_at": lock_data.get("started_at"),
        "updated_at": lock_data.get("updated_at"),
        "expires_at": lock_data.get("expires_at"),
        "stage": lock_data.get("stage"),
        "steps": lock_data.get("steps") or [],
        "error": bool(lock_data.get("error")),
    }
    return {
        "active": True,
        "task": task,
        "type": lock_data.get("type"),
        "message": lock_data.get("message") or "Opération système en cours...",
        "progress": lock_data.get("progress"),
        "stage": lock_data.get("stage"),
        "steps": lock_data.get("steps") or [],
        "error": bool(lock_data.get("error")),
    }


def _read_lock_raw():
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_lock(data):
    tmp_path = f"{LOCK_FILE}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, sort_keys=True)
    os.replace(tmp_path, LOCK_FILE)
    try:
        os.chmod(LOCK_FILE, 0o600)
    except OSError:
        pass


def _is_expired(data):
    try:
        expires_at = float(data.get("expires_at_ts") or 0)
    except (TypeError, ValueError):
        return True
    return expires_at <= _now()


def cleanup_expired_lock():
    data = _read_lock_raw()
    if not data or not _is_expired(data):
        return False
    release_lock(data.get("token"), force=True)
    return True


def get_system_status():
    data = _read_lock_raw()
    if data and _is_expired(data):
        release_lock(data.get("token"), force=True)
        data = None
    return _public_status(data)


def acquire_lock(task_type, message, *, progress=None, timeout_seconds=None, stage=None, steps=None):
    cleanup_expired_lock()
    token = uuid.uuid4().hex
    now = _now()
    ttl = _timeout_for(task_type, timeout_seconds)
    data = {
        "token": token,
        "type": task_type,
        "message": message,
        "progress": progress,
        "stage": stage,
        "steps": steps or [],
        "error": False,
        "started_at": _iso(now),
        "updated_at": _iso(now),
        "expires_at": _iso(now + ttl),
        "expires_at_ts": now + ttl,
    }
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(LOCK_FILE, flags, 0o600)
    except FileExistsError as exc:
        status = get_system_status()
        if not status.get("active"):
            return acquire_lock(task_type, message, progress=progress, timeout_seconds=timeout_seconds)
        active_message = status.get("message") or "Une opération système est déjà en cours."
        raise SystemTaskAlreadyRunning(active_message) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, sort_keys=True)
    return token


def update_lock(token, *, message=None, progress=None, timeout_seconds=None, stage=None, steps=None, error=None):
    data = _read_lock_raw()
    if not data or data.get("token") != token:
        return False
    now = _now()
    if message is not None:
        data["message"] = str(message)
    if progress is not None:
        data["progress"] = progress
    if stage is not None:
        data["stage"] = stage
    if steps is not None:
        data["steps"] = steps
    if error is not None:
        data["error"] = bool(error)
    data["updated_at"] = _iso(now)
    if timeout_seconds is not None:
        ttl = _timeout_for(data.get("type"), timeout_seconds)
        data["expires_at"] = _iso(now + ttl)
        data["expires_at_ts"] = now + ttl
    _write_lock(data)
    return True


def release_lock(token=None, *, force=False):
    data = _read_lock_raw()
    if not data:
        return False
    if not force and token and data.get("token") != token:
        return False
    if not force and not token:
        return False
    try:
        os.remove(LOCK_FILE)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


@contextmanager
def system_task_lock(task_type, message, *, progress=None, timeout_seconds=None, stage=None, steps=None):
    token = acquire_lock(
        task_type,
        message,
        progress=progress,
        timeout_seconds=timeout_seconds,
        stage=stage,
        steps=steps,
    )
    try:
        yield token
    finally:
        release_lock(token)
