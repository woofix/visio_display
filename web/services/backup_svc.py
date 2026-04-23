import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from urllib.parse import unquote, urlparse
from datetime import datetime, timezone

import constants as C
from db import db
from sqlalchemy import text


BACKUP_DIR = os.path.join(C.PRIVATE_DATA_DIR, "backups")
BACKUP_BASENAME_RE = re.compile(r"^visio-backup-\d{8}-\d{6}\.tar\.gz$")
MAX_BACKUPS = 5
BACKUP_FORMAT_VERSION = 3
BACKUP_MANIFEST = "manifest.json"
BACKUP_DB_DUMP = "postgres.dump"
BACKUP_MEDIA_ARCHIVE = "media.tar.gz"
BACKUP_PRIVATE_ARCHIVE = "private.tar.gz"
BACKUP_ENV_FILE = "env.backup"
ENV_FILE = os.path.join(C.BASE_DIR, ".env")
SUPPORTED_POSTGRES_MAJOR = 16
SUPPORTED_POSTGRES_IMAGE = "postgres:16.13-alpine"
UNSUPPORTED_SQL_SETTINGS = (
    "SET transaction_timeout = 0;",
)


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


def _run_command(command, *, env=None, missing_binary_message=None, failure_message=None):
    try:
        subprocess.run(command, check=True, env=env)
    except FileNotFoundError as exc:
        binary = command[0] if command else "commande inconnue"
        raise RuntimeError(
            missing_binary_message or (
                f"Outil système introuvable: {binary}. "
                "Reconstruisez les conteneurs Docker pour installer les outils PostgreSQL "
                "puis relancez la sauvegarde/restauration."
            )
        ) from exc
    except subprocess.CalledProcessError as exc:
        binary = command[0] if command else "commande inconnue"
        raise RuntimeError(
            failure_message or f"La commande {binary} a échoué avec le code {exc.returncode}."
        ) from exc


def _database_connection_parts():
    uri = db.engine.url
    return {
        "host": uri.host or "localhost",
        "port": int(uri.port or 5432),
        "database": uri.database,
        "username": uri.username or "",
        "password": uri.password or "",
    }


def _parse_postgres_major(version_value):
    version_text = str(version_value or "").strip()
    match = re.match(r"^(\d+)", version_text)
    if not match:
        raise RuntimeError(f"Version PostgreSQL illisible: {version_text or 'inconnue'}")
    return int(match.group(1))


def _database_server_version():
    version_text = db.session.execute(text("SHOW server_version")).scalar()
    return str(version_text or "").strip()


def _client_binary_version(binary_name):
    try:
        result = subprocess.run(
            [binary_name, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Outil système introuvable: {binary_name}. "
            "Reconstruisez les conteneurs Docker pour installer les outils PostgreSQL "
            "puis relancez la sauvegarde/restauration."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Impossible de lire la version de {binary_name} (code {exc.returncode})."
        ) from exc
    return (result.stdout or result.stderr or "").strip()


def _build_runtime_compatibility():
    server_version = _database_server_version()
    server_major = _parse_postgres_major(server_version)
    pg_dump_version = _client_binary_version("pg_dump")
    pg_restore_version = _client_binary_version("pg_restore")
    return {
        "supported_postgres_major": SUPPORTED_POSTGRES_MAJOR,
        "supported_postgres_image": SUPPORTED_POSTGRES_IMAGE,
        "server_version": server_version,
        "server_major": server_major,
        "pg_dump_version": pg_dump_version,
        "pg_restore_version": pg_restore_version,
    }


def _ensure_supported_runtime():
    runtime = _build_runtime_compatibility()
    if runtime["server_major"] != SUPPORTED_POSTGRES_MAJOR:
        raise RuntimeError(
            "Version PostgreSQL incompatible pour la sauvegarde/restauration: "
            f"serveur={runtime['server_version']}, "
            f"majeure attendue={SUPPORTED_POSTGRES_MAJOR}. "
            f"Mettez à niveau le service postgres vers {SUPPORTED_POSTGRES_IMAGE} avant de continuer."
        )
    return runtime


def _dump_postgres_database(output_path):
    _ensure_supported_runtime()
    parts = _database_connection_parts()
    env = os.environ.copy()
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]
    _run_command(
        [
            "pg_dump",
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            "--host",
            parts["host"],
            "--port",
            str(parts["port"]),
            "--username",
            parts["username"],
            "--file",
            output_path,
            parts["database"],
        ],
        env=env,
    )


def _restore_postgres_database(input_path):
    _ensure_supported_runtime()
    parts = _database_connection_parts()
    env = os.environ.copy()
    if parts["password"]:
        env["PGPASSWORD"] = parts["password"]
    with tempfile.TemporaryDirectory(prefix="visio-pg-restore-") as tmp_dir:
        restore_sql_path = os.path.join(tmp_dir, "restore.sql")
        sanitized_sql_path = os.path.join(tmp_dir, "restore.sanitized.sql")

        _run_command(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--file",
                restore_sql_path,
                input_path,
            ],
            env=env,
        )

        with open(restore_sql_path, "r", encoding="utf-8") as handle:
            restore_sql = handle.read()

        for statement in UNSUPPORTED_SQL_SETTINGS:
            restore_sql = restore_sql.replace(statement + "\n", "")
            restore_sql = restore_sql.replace(statement, "")

        with open(sanitized_sql_path, "w", encoding="utf-8") as handle:
            handle.write(restore_sql)

        _run_command(
            [
                "psql",
                "--set",
                "ON_ERROR_STOP=1",
                "--host",
                parts["host"],
                "--port",
                str(parts["port"]),
                "--username",
                parts["username"],
                "--dbname",
                parts["database"],
                "--file",
                sanitized_sql_path,
            ],
            env=env,
        )


def _archive_directory(source_dir, archive_path, *, progress_callback=None, exclude_dirs=None):
    exclude_dirs = {os.path.abspath(path) for path in (exclude_dirs or [])}
    base_dir = os.path.abspath(source_dir)
    if not os.path.isdir(base_dir):
        _emit_progress(progress_callback, f"Source absente, section ignorée: {source_dir}")
        return False

    with tarfile.open(archive_path, "w:gz") as archive:
        for root, dirs, files in os.walk(base_dir):
            current_root = os.path.abspath(root)
            dirs[:] = [
                name for name in dirs
                if os.path.abspath(os.path.join(current_root, name)) not in exclude_dirs
            ]
            rel_root = os.path.relpath(current_root, base_dir)
            if rel_root != ".":
                archive.add(current_root, arcname=rel_root, recursive=False)
            for filename in files:
                source_path = os.path.join(current_root, filename)
                archive.add(source_path, arcname=os.path.relpath(source_path, base_dir), recursive=False)
    return True


def _write_manifest(target_dir, runtime):
    manifest_path = os.path.join(target_dir, BACKUP_MANIFEST)
    payload = {
        "version": BACKUP_FORMAT_VERSION,
        "created_at": _utc_now().isoformat(),
        "database_dump": BACKUP_DB_DUMP,
        "media_archive": BACKUP_MEDIA_ARCHIVE,
        "private_archive": BACKUP_PRIVATE_ARCHIVE,
        "env_file": BACKUP_ENV_FILE if os.path.isfile(ENV_FILE) else None,
        "postgres_server_version": runtime["server_version"],
        "postgres_server_major": runtime["server_major"],
        "postgres_supported_major": runtime["supported_postgres_major"],
        "postgres_supported_image": runtime["supported_postgres_image"],
        "pg_dump_version": runtime["pg_dump_version"],
        "pg_restore_version": runtime["pg_restore_version"],
    }
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _build_backup_payload(target_dir, progress_callback=None):
    runtime = _ensure_supported_runtime()
    db_dump_path = os.path.join(target_dir, BACKUP_DB_DUMP)
    media_archive_path = os.path.join(target_dir, BACKUP_MEDIA_ARCHIVE)
    private_archive_path = os.path.join(target_dir, BACKUP_PRIVATE_ARCHIVE)

    _emit_progress(progress_callback, "Export PostgreSQL...")
    _dump_postgres_database(db_dump_path)
    _emit_progress(progress_callback, "Dump PostgreSQL terminé.")

    _emit_progress(progress_callback, "Archivage des médias...")
    _archive_directory(C.STATIC_MEDIA_DIR, media_archive_path, progress_callback=progress_callback)
    _emit_progress(progress_callback, "Médias archivés.")

    _emit_progress(progress_callback, "Archivage des fichiers privés...")
    _archive_directory(
        C.PRIVATE_DATA_DIR,
        private_archive_path,
        progress_callback=progress_callback,
        exclude_dirs=[BACKUP_DIR],
    )
    _emit_progress(progress_callback, "Fichiers privés archivés.")

    if os.path.isfile(ENV_FILE):
        shutil.copy2(ENV_FILE, os.path.join(target_dir, BACKUP_ENV_FILE))
        _emit_progress(progress_callback, "Copie du .env ajoutée.")

    _write_manifest(target_dir, runtime)


def _add_tree_to_archive(archive, source_path, archive_name, progress_callback=None):
    if not os.path.exists(source_path):
        return
    _emit_progress(progress_callback, f"Ajout de {archive_name} à l'archive...")
    archive.add(source_path, arcname=archive_name)
    _emit_progress(progress_callback, f"Section archivée: {archive_name}")


def create_backup_archive(progress_callback=None):
    _ensure_backup_dir()
    filename = _timestamped_backup_name()
    archive_file = os.path.join(BACKUP_DIR, filename)
    _emit_progress(progress_callback, "Initialisation de la sauvegarde...")
    _emit_progress(progress_callback, f"Archive cible: {filename}")

    with tempfile.TemporaryDirectory(prefix="visio-backup-build-") as tmp_dir:
        _build_backup_payload(tmp_dir, progress_callback=progress_callback)

        with tarfile.open(archive_file, "w:gz") as archive:
            for entry in sorted(os.listdir(tmp_dir)):
                _add_tree_to_archive(
                    archive,
                    os.path.join(tmp_dir, entry),
                    entry,
                    progress_callback=progress_callback,
                )

    _emit_progress(progress_callback, "Nettoyage des anciennes sauvegardes...")
    _prune_old_backups()
    stat = os.stat(archive_file)
    backup = _backup_metadata(filename, stat)
    backup["path"] = archive_file
    _emit_progress(progress_callback, "Sauvegarde finalisée.")
    return backup


def _parse_smb_url(raw_url):
    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme.lower() != "smb":
        raise RuntimeError("Lien SMB invalide: utilisez une adresse de type smb://serveur/partage/dossier.")
    if not parsed.hostname:
        raise RuntimeError("Lien SMB invalide: le nom du serveur est requis.")

    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not path_parts:
        raise RuntimeError("Lien SMB invalide: le nom du partage est requis.")

    return {
        "server": parsed.hostname,
        "port": parsed.port,
        "share": path_parts[0],
        "remote_dir": "/".join(path_parts[1:]).strip("/"),
        "url_username": unquote(parsed.username or ""),
        "url_password": unquote(parsed.password or ""),
    }


def _split_smb_username(raw_username):
    value = str(raw_username or "").strip()
    if "\\" in value:
        domain, username = value.split("\\", 1)
        return domain.strip(), username.strip()
    if "/" in value:
        domain, username = value.split("/", 1)
        return domain.strip(), username.strip()
    return "", value


def copy_backup_to_smb(source_path, backup_filename, remote_settings, progress_callback=None):
    smb = _parse_smb_url((remote_settings or {}).get("url", ""))
    username = str((remote_settings or {}).get("username", "") or smb["url_username"]).strip()
    password = str((remote_settings or {}).get("password", "") or smb["url_password"]).strip()

    _emit_progress(progress_callback, f"Copie SMB vers //{smb['server']}/{smb['share']}...")

    with tempfile.TemporaryDirectory(prefix="visio-backup-smb-") as tmp_dir:
        command = ["smbclient", f"//{smb['server']}/{smb['share']}"]
        if smb["port"]:
            command.extend(["-p", str(smb["port"])])

        if username or password:
            domain, smb_username = _split_smb_username(username)
            auth_path = os.path.join(tmp_dir, "smb-credentials")
            with open(auth_path, "w", encoding="utf-8") as handle:
                handle.write(f"username = {smb_username}\n")
                handle.write(f"password = {password}\n")
                if domain:
                    handle.write(f"domain = {domain}\n")
            os.chmod(auth_path, 0o600)
            command.extend(["-A", auth_path])
        else:
            command.append("-N")

        if smb["remote_dir"]:
            command.extend(["-D", smb["remote_dir"]])

        command.extend(["-c", f'put "{source_path}" "{backup_filename}"'])
        _run_command(
            command,
            missing_binary_message=(
                "Outil système introuvable: smbclient. "
                "Installez le client SMB/CIFS dans le conteneur puis relancez la copie de sauvegarde."
            ),
            failure_message=(
                "La copie SMB de la sauvegarde a échoué. "
                "Vérifiez le lien smb://, les identifiants et que le dossier distant existe."
            ),
        )

    _emit_progress(progress_callback, f"Copie SMB terminée: {backup_filename}")


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


def _replace_directory_contents(source_dir, destination_dir, *, preserve_names=None):
    preserve_names = set(preserve_names or [])
    os.makedirs(destination_dir, exist_ok=True)

    for entry in os.listdir(destination_dir):
        if entry in preserve_names:
            continue
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


def _extract_directory_archive(archive_path, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as archive:
        _safe_extract_tar(archive, target_dir)


def _ensure_runtime_directories():
    for path in (
        C.STATIC_MEDIA_DIR,
        C.UPLOAD_FOLDER,
        C.VIDEO_THUMB_FOLDER,
        C.IMAGE_VARIANT_FOLDER,
        C.VIDEO_VARIANT_FOLDER,
        C.VIDEO_POSTER_FOLDER,
        C.PRIVATE_DATA_DIR,
        BACKUP_DIR,
    ):
        os.makedirs(path, exist_ok=True)


def _restore_env_file(extracted_root):
    env_backup_path = os.path.join(extracted_root, BACKUP_ENV_FILE)
    if not os.path.isfile(env_backup_path):
        return
    try:
        shutil.copy2(env_backup_path, ENV_FILE)
    except OSError:
        return


def _load_manifest(extracted_root):
    manifest_path = os.path.join(extracted_root, BACKUP_MANIFEST)
    if not os.path.isfile(manifest_path):
        raise RuntimeError("Sauvegarde invalide: manifest.json est introuvable.")
    with open(manifest_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _validate_manifest(manifest):
    backup_version = int(manifest.get("version") or 0)
    if backup_version != BACKUP_FORMAT_VERSION:
        raise RuntimeError(
            "Format de sauvegarde incompatible: "
            f"archive={backup_version}, attendu={BACKUP_FORMAT_VERSION}."
        )

    backup_major = int(manifest.get("postgres_supported_major") or 0)
    if backup_major != SUPPORTED_POSTGRES_MAJOR:
        raise RuntimeError(
            "Sauvegarde incompatible avec cette image: "
            f"majeure PostgreSQL archive={backup_major}, "
            f"majeure attendue={SUPPORTED_POSTGRES_MAJOR}."
        )

    runtime = _ensure_supported_runtime()
    if runtime["server_major"] != backup_major:
        raise RuntimeError(
            "Serveur PostgreSQL incompatible avec la sauvegarde: "
            f"serveur={runtime['server_version']}, archive={backup_major}."
        )
    return runtime


def restore_backup_archive(uploaded_file):
    _ensure_backup_dir()

    db.session.remove()
    db.engine.dispose()

    with tempfile.TemporaryDirectory(prefix="visio-restore-") as tmp_dir:
        uploaded_path = os.path.join(tmp_dir, _normalize_filename(uploaded_file.filename or "backup.tar.gz"))
        uploaded_file.save(uploaded_path)

        with tarfile.open(uploaded_path, "r:gz") as archive:
            _safe_extract_tar(archive, tmp_dir)
        manifest = _load_manifest(tmp_dir)
        _validate_manifest(manifest)

        extracted_media_dir = os.path.join(tmp_dir, "media")
        extracted_private_dir = os.path.join(tmp_dir, "private")
        media_archive_path = os.path.join(tmp_dir, BACKUP_MEDIA_ARCHIVE)
        private_archive_path = os.path.join(tmp_dir, BACKUP_PRIVATE_ARCHIVE)
        db_dump_path = os.path.join(tmp_dir, BACKUP_DB_DUMP)

        if not os.path.isfile(db_dump_path):
            raise RuntimeError("Sauvegarde invalide: le dump PostgreSQL est introuvable.")
        if not os.path.isfile(media_archive_path):
            raise RuntimeError("Sauvegarde invalide: l'archive des médias est introuvable.")
        if not os.path.isfile(private_archive_path):
            raise RuntimeError("Sauvegarde invalide: l'archive des fichiers privés est introuvable.")

        if os.path.isfile(media_archive_path):
            extracted_media_dir = os.path.join(tmp_dir, "restore-media")
            _extract_directory_archive(media_archive_path, extracted_media_dir)
        if os.path.isfile(private_archive_path):
            extracted_private_dir = os.path.join(tmp_dir, "restore-private")
            _extract_directory_archive(private_archive_path, extracted_private_dir)
        if os.path.isfile(db_dump_path):
            _restore_postgres_database(db_dump_path)

        _replace_directory_contents(extracted_media_dir, C.STATIC_MEDIA_DIR)
        _replace_directory_contents(
            extracted_private_dir,
            C.PRIVATE_DATA_DIR,
            preserve_names={os.path.basename(BACKUP_DIR)},
        )
        _ensure_runtime_directories()
        _restore_env_file(tmp_dir)
