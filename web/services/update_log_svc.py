# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import re
import time
from datetime import datetime

import constants as C


UPDATE_LOG_DIR = os.path.join(C.PRIVATE_DATA_DIR, "update_logs")
UPDATE_LOG_RETENTION_DAYS = 15
UPDATE_LOG_TAIL_SCAN_BYTES = 4096
_FILENAME_RE = re.compile(r"^update-(?P<branch>[A-Za-z0-9_.-]+)-(?P<stamp>\d{8}-\d{6})\.log$")
_STATUS_RE = re.compile(r"^STATUS=(?P<status>\w+) EXIT_CODE=(?P<code>-?\d+)\s*$", re.MULTILINE)


def _ensure_log_dir():
    os.makedirs(UPDATE_LOG_DIR, exist_ok=True)


def _is_allowed_log_name(filename):
    return bool(_FILENAME_RE.match(filename or ""))


def _prune_old_logs():
    if not os.path.isdir(UPDATE_LOG_DIR):
        return
    cutoff = time.time() - UPDATE_LOG_RETENTION_DAYS * 86400
    for entry in os.listdir(UPDATE_LOG_DIR):
        if not _is_allowed_log_name(entry):
            continue
        path = os.path.join(UPDATE_LOG_DIR, entry)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            continue


def _read_status(path):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as handle:
            handle.seek(max(0, size - UPDATE_LOG_TAIL_SCAN_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return "unknown", None
    match = _STATUS_RE.search(tail)
    if not match:
        return "unknown", None
    return match.group("status"), int(match.group("code"))


def log_path(filename):
    safe_name = os.path.basename((filename or "").replace("\\", "/"))
    if safe_name != filename or not _is_allowed_log_name(safe_name):
        raise FileNotFoundError(filename)
    path = os.path.join(UPDATE_LOG_DIR, safe_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(filename)
    return path


def read_update_log(filename):
    path = log_path(filename)
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def list_update_logs():
    _ensure_log_dir()
    _prune_old_logs()
    entries = []
    for entry in os.listdir(UPDATE_LOG_DIR):
        match = _FILENAME_RE.match(entry)
        if not match:
            continue
        path = os.path.join(UPDATE_LOG_DIR, entry)
        if not os.path.isfile(path):
            continue
        status, exit_code = _read_status(path)
        try:
            started_at = datetime.strptime(match.group("stamp"), "%Y%m%d-%H%M%S")
            timestamp_display = started_at.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            started_at = datetime.fromtimestamp(0)
            timestamp_display = entry
        entries.append({
            "filename": entry,
            "branch": match.group("branch"),
            "timestamp_display": timestamp_display,
            "status": status,
            "exit_code": exit_code,
            "size_bytes": os.path.getsize(path),
            "_sort_key": started_at,
        })
    entries.sort(key=lambda item: item["_sort_key"], reverse=True)
    for item in entries:
        del item["_sort_key"]
    return entries
