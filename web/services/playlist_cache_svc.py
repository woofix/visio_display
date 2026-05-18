# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import threading
from datetime import datetime

from constants import (
    IMAGE_VARIANT_FOLDER,
    MEDIA_EXTS,
    UPLOAD_FOLDER,
    VIDEO_POSTER_FOLDER,
    VIDEO_THUMB_FOLDER,
    VIDEO_VARIANT_FOLDER,
)

_CACHE = {}
_MAX_CACHE_ENTRIES = 256
_LOCK = threading.Lock()
_MEDIA_REVISION = None
_MEDIA_FOLDER_MARKER = None


def _folder_revision(folder, *, allowed_exts=None):
    if not os.path.isdir(folder):
        return (0, 0, 0)
    file_count = 0
    total_size = 0
    latest_mtime_ns = 0
    try:
        entries = os.scandir(folder)
    except OSError:
        return (0, 0, 0)
    with entries:
        for entry in entries:
            try:
                if not entry.is_file():
                    continue
                if allowed_exts and not entry.name.lower().endswith(allowed_exts):
                    continue
                stat = entry.stat()
            except OSError:
                continue
            file_count += 1
            total_size += stat.st_size
            latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
    return (file_count, total_size, latest_mtime_ns)


def _folder_marker(folder):
    try:
        stat = os.stat(folder)
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def make_config_revision(cfg):
    return str(cfg.get("_config_revision", 0) or 0)


def make_media_revision(*, force=False):
    global _MEDIA_REVISION, _MEDIA_FOLDER_MARKER
    marker = (
        _folder_marker(UPLOAD_FOLDER),
        _folder_marker(IMAGE_VARIANT_FOLDER),
        _folder_marker(VIDEO_THUMB_FOLDER),
        _folder_marker(VIDEO_POSTER_FOLDER),
        _folder_marker(VIDEO_VARIANT_FOLDER),
    )
    with _LOCK:
        if (
            not force
            and _MEDIA_REVISION is not None
            and marker == _MEDIA_FOLDER_MARKER
        ):
            return _MEDIA_REVISION

    revision = (
        _folder_revision(UPLOAD_FOLDER, allowed_exts=MEDIA_EXTS),
        _folder_revision(IMAGE_VARIANT_FOLDER),
        _folder_revision(VIDEO_THUMB_FOLDER),
        _folder_revision(VIDEO_POSTER_FOLDER),
        _folder_revision(VIDEO_VARIANT_FOLDER),
    )
    with _LOCK:
        _MEDIA_REVISION = revision
        _MEDIA_FOLDER_MARKER = marker
    return revision


def bump_media_revision():
    return make_media_revision(force=True)


def make_playlist_revision(cfg):
    return {
        "config": make_config_revision(cfg),
        "media": make_media_revision(),
        "time": make_time_signature(),
    }


def make_time_signature():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def get_cached_playlist(cache_key, config_signature, media_signature, builder):
    fingerprint = (config_signature, media_signature)
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] == fingerprint:
            return [dict(item) for item in cached[1]]

    playlist = builder()
    snapshot = [dict(item) for item in playlist]
    with _LOCK:
        _CACHE[cache_key] = (fingerprint, snapshot)
        while len(_CACHE) > _MAX_CACHE_ENTRIES:
            _CACHE.pop(next(iter(_CACHE)))
    return [dict(item) for item in snapshot]


def clear_playlist_cache():
    with _LOCK:
        _CACHE.clear()
