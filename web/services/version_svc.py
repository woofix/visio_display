# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import re
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from constants import PRIVATE_DATA_DIR


SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_CWD = os.path.normpath(os.path.join(SERVICE_DIR, "..", ".."))
VERSION_CACHE_FILE = os.path.join(PRIVATE_DATA_DIR, "version_check.json")
DEFAULT_VERSION_URL = "https://api.github.com/repos/woofix/visio_display/releases/latest"
DEFAULT_CACHE_SECONDS = 1800
DEFAULT_FAILURE_CACHE_SECONDS = 300
VERSION_PATTERN = re.compile(r"^v?(\d+(?:\.\d+){1,3})$")


def _now():
    return int(time.time())


def _cache_ttl_seconds():
    try:
        return max(300, int(os.environ.get("VISIO_VERSION_CHECK_TTL_SECONDS", DEFAULT_CACHE_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_CACHE_SECONDS


def _version_url():
    return os.environ.get("VISIO_VERSION_URL", "").strip() or DEFAULT_VERSION_URL


def _clean_version(version):
    value = str(version or "").strip()
    match = VERSION_PATTERN.match(value)
    if not match:
        return ""
    return match.group(1)


def _extract_remote_version(payload):
    value = str(payload or "").strip()
    if not value:
        return ""
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return _clean_version(value)
    if not isinstance(data, dict):
        return ""
    for key in ("tag_name", "name"):
        remote_version = _clean_version(data.get(key, ""))
        if remote_version:
            return remote_version
    return ""


def _version_parts(version):
    parts = []
    for item in _clean_version(version).split("."):
        try:
            parts.append(int(item))
        except ValueError:
            break
    return tuple(parts)


def _compare_versions(local_version, remote_version):
    local_parts = _version_parts(local_version)
    remote_parts = _version_parts(remote_version)
    if not local_parts or not remote_parts:
        return 0
    length = max(len(local_parts), len(remote_parts))
    local_parts = local_parts + (0,) * (length - len(local_parts))
    remote_parts = remote_parts + (0,) * (length - len(remote_parts))
    if remote_parts > local_parts:
        return 1
    if remote_parts < local_parts:
        return -1
    return 0


def _read_local_version():
    env_version = os.environ.get("APP_VERSION", "").strip()
    if env_version:
        return env_version
    version_files = []
    git_root = os.environ.get("VISIO_GIT_ROOT", "").strip()
    if git_root:
        version_files.append(os.path.join(git_root, "VERSION"))
    version_files.append(os.path.join(DEFAULT_REPO_CWD, "VERSION"))
    version_files.append("/VERSION")

    seen = set()
    for version_file in version_files:
        version_file = os.path.normpath(version_file)
        if version_file in seen:
            continue
        seen.add(version_file)
        try:
            with open(version_file, "r", encoding="utf-8") as handle:
                version = handle.read().strip()
            if version:
                return version
        except OSError:
            continue
    return ""


def _read_remote_version_with_curl(version_url, timeout=6):
    curl_path = shutil.which("curl")
    if not curl_path:
        return "", "source de version inaccessible"
    try:
        result = subprocess.run(
            [
                curl_path,
                "-fsSL",
                "--max-time",
                str(timeout),
                "-A",
                "visio-display-version-check",
                version_url,
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout + 1,
        )
    except (OSError, subprocess.SubprocessError):
        return "", "source de version inaccessible"
    if result.returncode != 0:
        return "", "source de version inaccessible"
    remote_version = _extract_remote_version(result.stdout[:8192])
    if not remote_version:
        return "", "version distante illisible"
    return remote_version, ""


def _read_remote_version(timeout=6):
    version_url = _version_url()
    request = Request(version_url, headers={"User-Agent": "visio-display-version-check"})
    try:
        with urlopen(request, timeout=timeout) as response:
            remote_version = _extract_remote_version(response.read(8192).decode("utf-8", errors="replace"))
            if not remote_version:
                return "", "version distante illisible"
            return remote_version, ""
    except HTTPError as exc:
        return "", f"source indisponible ({exc.code})"
    except URLError:
        return _read_remote_version_with_curl(version_url, timeout=timeout)
    except OSError as exc:
        return "", str(exc)


def _read_cache():
    try:
        from flask import has_app_context
        from db import VersionCheckCache, db
    except ImportError:
        has_app_context = None
    if has_app_context and has_app_context():
        row = db.session.get(VersionCheckCache, _version_url())
        return row.to_dict() if row is not None else {}
    try:
        with open(VERSION_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {}
        return payload
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(payload):
    source_url = str(payload.get("source_url") or _version_url()).strip()
    try:
        from flask import has_app_context
        from db import VersionCheckCache, db
    except ImportError:
        has_app_context = None
    if has_app_context and has_app_context():
        row = db.session.get(VersionCheckCache, source_url)
        if row is None:
            row = VersionCheckCache(source_url=source_url)
            db.session.add(row)
        row.remote_version = _clean_version(payload.get("remote_version", ""))
        row.fetch_error = str(payload.get("fetch_error") or "")
        try:
            row.fetched_at = int(payload.get("fetched_at") or 0)
        except (TypeError, ValueError):
            row.fetched_at = 0
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return False
        return True
    try:
        os.makedirs(os.path.dirname(VERSION_CACHE_FILE), exist_ok=True)
        tmp_path = f"{VERSION_CACHE_FILE}.{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, VERSION_CACHE_FILE)
    except OSError:
        return False
    return True


def _cache_fetched_at(cached):
    try:
        return int(cached.get("fetched_at") or 0)
    except (TypeError, ValueError):
        return 0


def _cache_is_fresh(cached, now):
    if cached.get("source_url") != _version_url():
        return False
    fetched_at = _cache_fetched_at(cached)
    if fetched_at <= 0 or fetched_at > now + 60:
        return False
    ttl = _cache_ttl_seconds()
    cached_remote_version = _clean_version(cached.get("remote_version", ""))
    cached_fetch_error = cached.get("fetch_error", "")
    if not cached_remote_version and cached_fetch_error:
        ttl = DEFAULT_FAILURE_CACHE_SECONDS
    return now - fetched_at < ttl


def get_version_status(force_refresh=False, allow_remote=True):
    now = _now()
    version_url = _version_url()
    local_version = _read_local_version()
    cached = _read_cache()
    fetched_at = _cache_fetched_at(cached)
    source_matches_cache = cached.get("source_url") == version_url
    cached_remote_version = _clean_version(cached.get("remote_version", "")) if source_matches_cache else ""
    if not force_refresh and cached and _cache_is_fresh(cached, now):
        remote_version = cached_remote_version
        fetch_error = cached.get("fetch_error", "")
        fetched_from_cache = True
    elif not allow_remote:
        remote_version = cached_remote_version
        fetch_error = cached.get("fetch_error", "") if source_matches_cache else ""
        fetched_from_cache = bool(cached_remote_version or fetch_error)
    else:
        previous_remote_version = cached_remote_version
        remote_version, fetch_error = _read_remote_version()
        cached_remote_version = remote_version or previous_remote_version
        fetched_from_cache = False
        _write_cache({
            "remote_version": cached_remote_version,
            "fetch_error": fetch_error,
            "fetched_at": now,
            "source_url": version_url,
        })
        remote_version = cached_remote_version

    remote_version = _clean_version(remote_version)
    info = {
        "status": "check_failed",
        "status_label": "Check failed",
        "status_tone": "warning",
        "local_version": local_version,
        "remote_version": remote_version,
        "fetch_error": fetch_error,
        "fetched_from_cache": fetched_from_cache,
        "fetched_at": fetched_at if fetched_from_cache else now,
    }
    if not remote_version:
        return info

    comparison = _compare_versions(local_version, remote_version)
    if comparison > 0:
        info.update({
            "status": "update_available",
            "status_label": "Update available",
            "status_tone": "warning",
        })
    elif comparison < 0:
        info.update({
            "status": "local_ahead",
            "status_label": "Local version ahead",
            "status_tone": "info",
        })
    else:
        info.update({
            "status": "up_to_date",
            "status_label": "Up to date",
            "status_tone": "success",
        })
    return info
