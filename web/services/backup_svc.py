import os
import re
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone

import constants as C
from db import db


BACKUP_DIR = os.path.join(C.PRIVATE_DATA_DIR, "backups")
BACKUP_BASENAME_RE = re.compile(r"^visio-backup-\d{8}-\d{6}\.tar\.gz$")
MAX_BACKUPS = 5


def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def _utc_now():
    return datetime.now(timezone.utc)


def _timestamped_backup_name():
    return _utc_now().strftime("visio-backup-%Y%m%d-%H%M%S.tar.gz")


def _is_allowed_backup_name(filename):
    return bool(BACKUP_BASENAME_RE.match(filename or ""))


def _normalize_filename(filename):
    return os.path.basename((filename or "").replace("\\", "/"))


def backup_path(filename):
    safe_name = _normalize_filename(filename)
    if safe_name != filename or not _is_allowed_backup_name(safe_name):
        raise FileNotFoundError(filename)
    path = os.path.join(BACKUP_DIR, safe_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(filename)
    return path


def _backup_metadata(filename, stat_result):
    created_at = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
    return {
        "filename": filename,
        "size": stat_result.st_size,
        "size_bytes": stat_result.st_size,
        "created_at": created_at,
        "created_at_iso": created_at.isoformat(),
    }


def _emit_progress(progress_callback, message):
    if progress_callback is not None:
        progress_callback(message)


def list_backups():
    _ensure_backup_dir()
    items = []
    for entry in os.listdir(BACKUP_DIR):
        path = os.path.join(BACKUP_DIR, entry)
        if not os.path.isfile(path) or not _is_allowed_backup_name(entry):
            continue
        items.append(_backup_metadata(entry, os.stat(path)))
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


def _prune_old_backups():
    backups = list_backups()
    for item in backups[MAX_BACKUPS:]:
        target = os.path.join(BACKUP_DIR, item["filename"])
        try:
            os.remove(target)
        except FileNotFoundError:
            continue


def _add_tree_to_archive(archive, source_dir, archive_root, progress_callback=None):
    if not os.path.isdir(source_dir):
        _emit_progress(progress_callback, f"Source absente, section ignorée: {archive_root}")
        return
    _emit_progress(progress_callback, f"Ajout de {archive_root} à l'archive...")
    archive.add(source_dir, arcname=archive_root)
    _emit_progress(progress_callback, f"Section archivée: {archive_root}")


def create_backup_archive(progress_callback=None):
    _ensure_backup_dir()
    filename = _timestamped_backup_name()
    archive_file = os.path.join(BACKUP_DIR, filename)
    _emit_progress(progress_callback, "Initialisation de la sauvegarde...")
    _emit_progress(progress_callback, f"Archive cible: {filename}")

    with tarfile.open(archive_file, "w:gz") as archive:
        _add_tree_to_archive(archive, C.STATIC_MEDIA_DIR, "media", progress_callback=progress_callback)
        _add_tree_to_archive(archive, C.PRIVATE_DATA_DIR, "private", progress_callback=progress_callback)

    _emit_progress(progress_callback, "Nettoyage des anciennes sauvegardes...")
    _prune_old_backups()
    stat = os.stat(archive_file)
    backup = _backup_metadata(filename, stat)
    backup["path"] = archive_file
    _emit_progress(progress_callback, "Sauvegarde finalisée.")
    return backup


def delete_backup_archive(filename):
    path = backup_path(filename)
    os.remove(path)


def _safe_extract_tar(archive, target_dir):
    target_dir = os.path.abspath(target_dir)
    for member in archive.getmembers():
        member_path = os.path.abspath(os.path.join(target_dir, member.name))
        if os.path.commonpath([target_dir, member_path]) != target_dir:
            raise ValueError("Unsafe path detected in backup archive")
    archive.extractall(target_dir)


def _replace_directory_contents(source_dir, destination_dir):
    os.makedirs(destination_dir, exist_ok=True)

    for entry in os.listdir(destination_dir):
        target = os.path.join(destination_dir, entry)
        if os.path.isdir(target) and not os.path.islink(target):
            shutil.rmtree(target)
        else:
            os.remove(target)

    if not os.path.isdir(source_dir):
        return

    for entry in os.listdir(source_dir):
        src = os.path.join(source_dir, entry)
        dst = os.path.join(destination_dir, entry)
        shutil.move(src, dst)


def restore_backup_archive(uploaded_file):
    _ensure_backup_dir()

    db.session.remove()
    db.engine.dispose()

    with tempfile.TemporaryDirectory(prefix="visio-restore-") as tmp_dir:
        uploaded_path = os.path.join(tmp_dir, _normalize_filename(uploaded_file.filename or "backup.tar.gz"))
        uploaded_file.save(uploaded_path)

        with tarfile.open(uploaded_path, "r:gz") as archive:
            _safe_extract_tar(archive, tmp_dir)

        extracted_media_dir = os.path.join(tmp_dir, "media")
        extracted_private_dir = os.path.join(tmp_dir, "private")

        _replace_directory_contents(extracted_media_dir, C.STATIC_MEDIA_DIR)
        _replace_directory_contents(extracted_private_dir, C.PRIVATE_DATA_DIR)
