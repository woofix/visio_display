# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from constants import PRIVATE_DATA_DIR


SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_CWD = os.path.normpath(os.path.join(SERVICE_DIR, "..", ".."))
VERSION_CACHE_FILE = os.path.join(PRIVATE_DATA_DIR, "version_check.json")
DEFAULT_VERSION_URL = "https://raw.githubusercontent.com/woofix/visio_display/main/VERSION"
DEFAULT_CACHE_SECONDS = 1800


def _now():
    return int(time.time())


def _cache_ttl_seconds():
    try:
        return max(300, int(os.environ.get("VISIO_VERSION_CHECK_TTL_SECONDS", DEFAULT_CACHE_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_CACHE_SECONDS


def _clean_version(version):
    return str(version or "").strip().lstrip("v")


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
    version_file = os.path.normpath(os.path.join(DEFAULT_REPO_CWD, "VERSION"))
    try:
        with open(version_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
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
    return result.stdout[:128].strip(), ""


def _read_remote_version(timeout=6):
    version_url = os.environ.get("VISIO_VERSION_URL", "").strip() or DEFAULT_VERSION_URL
    request = Request(version_url, headers={"User-Agent": "visio-display-version-check"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(128).decode("utf-8", errors="replace").strip(), ""
    except HTTPError as exc:
        return "", f"source indisponible ({exc.code})"
    except URLError:
        return _read_remote_version_with_curl(version_url, timeout=timeout)
    except OSError as exc:
        return "", str(exc)


def _read_cache():
    try:
        with open(VERSION_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            return {}
        return payload
    except (OSError, ValueError, TypeError):
        return {}


def _write_cache(payload):
    os.makedirs(os.path.dirname(VERSION_CACHE_FILE), exist_ok=True)
    tmp_path = f"{VERSION_CACHE_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, VERSION_CACHE_FILE)


def get_version_status():
    local_version = _read_local_version()
    cached = _read_cache()
    fetched_at = int(cached.get("fetched_at") or 0)
    cached_remote_version = _clean_version(cached.get("remote_version", ""))
    cached_fetch_error = cached.get("fetch_error", "")
    has_usable_cache = bool(cached_remote_version or not cached_fetch_error)
    if cached and has_usable_cache and _now() - fetched_at < _cache_ttl_seconds():
        remote_version = cached.get("remote_version", "")
        fetch_error = cached.get("fetch_error", "")
        fetched_from_cache = True
    else:
        previous_remote_version = cached_remote_version
        remote_version, fetch_error = _read_remote_version()
        remote_version = _clean_version(remote_version)
        cached_remote_version = remote_version or previous_remote_version
        fetched_from_cache = False
        _write_cache({
            "remote_version": cached_remote_version,
            "fetch_error": fetch_error,
            "fetched_at": _now(),
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
        "fetched_at": fetched_at if fetched_from_cache else _now(),
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
