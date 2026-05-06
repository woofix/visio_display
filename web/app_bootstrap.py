# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import logging
import os
import secrets
import shutil
from datetime import timedelta

from flask import abort, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

import constants as C
from constants import (
    ALL_PERMISSIONS,
    IMAGE_VARIANT_FOLDER,
    LEGACY_STATIC_MEDIA_DIR,
    LEGACY_IMAGE_VARIANT_FOLDER,
    LEGACY_VIDEO_POSTER_FOLDER,
    LEGACY_VIDEO_THUMB_FOLDER,
    LEGACY_VIDEO_VARIANT_FOLDER,
    VIDEO_POSTER_FOLDER,
    VIDEO_THUMB_FOLDER,
    VIDEO_VARIANT_FOLDER,
    UPLOAD_FOLDER,
)
from db import db
from services.config_svc import (
    get_default_screen_name,
    get_screen_halo_color,
    halo_color_to_rgb,
    is_feature_enabled,
    load_config,
)
from services.i18n import _flash, _trans, get_language
from services.rbac_svc import init_rbac
from services.users_svc import get_user, has_permission, init_users, is_superadmin, load_users
from translations import TRANSLATIONS


LOGGER = logging.getLogger(__name__)


CLIENT_HEARTBEAT_EXTRA_COLUMNS = {
    "client_version": "VARCHAR(64) NOT NULL DEFAULT ''",
    "uptime_seconds": "INTEGER",
    "cpu_load_percent": "FLOAT",
    "ram_used_mb": "INTEGER",
    "ram_total_mb": "INTEGER",
    "temperature_c": "FLOAT",
    "disk_free_mb": "INTEGER",
    "disk_total_mb": "INTEGER",
    "resolution": "VARCHAR(64) NOT NULL DEFAULT ''",
    "last_error": "VARCHAR(512) NOT NULL DEFAULT ''",
}

SCHEMA_MIGRATIONS = (
    {
        "table": "client_heartbeats",
        "columns": CLIENT_HEARTBEAT_EXTRA_COLUMNS,
    },
    {
        "table": "users",
        "columns": {
            "must_change_password": "BOOLEAN NOT NULL DEFAULT false",
        },
    },
)


def env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_csv(name):
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def migrate_legacy_storage():
    _migrate_legacy_media_root(LEGACY_STATIC_MEDIA_DIR)
    _migrate_current_media_root_to_original()

    for legacy_dir, current_dir in (
        (LEGACY_VIDEO_THUMB_FOLDER, VIDEO_THUMB_FOLDER),
        (LEGACY_IMAGE_VARIANT_FOLDER, IMAGE_VARIANT_FOLDER),
        (LEGACY_VIDEO_POSTER_FOLDER, VIDEO_POSTER_FOLDER),
        (LEGACY_VIDEO_VARIANT_FOLDER, VIDEO_VARIANT_FOLDER),
    ):
        _migrate_legacy_rendition_dir(legacy_dir, current_dir)


def _migrate_legacy_media_root(legacy_root):
    if not os.path.isdir(legacy_root) or os.path.abspath(legacy_root) == os.path.abspath(UPLOAD_FOLDER):
        return
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    skipped_names = {
        "visio-display.db",
        "config.json",
        "queue.json",
        "users.json",
        os.path.basename(LEGACY_VIDEO_THUMB_FOLDER),
        os.path.basename(LEGACY_IMAGE_VARIANT_FOLDER),
        os.path.basename(LEGACY_VIDEO_POSTER_FOLDER),
        os.path.basename(LEGACY_VIDEO_VARIANT_FOLDER),
    }

    for entry in os.listdir(legacy_root):
        if entry in skipped_names:
            continue
        legacy_path = os.path.join(legacy_root, entry)
        current_path = os.path.join(UPLOAD_FOLDER, entry)
        if os.path.exists(current_path):
            continue
        try:
            shutil.move(legacy_path, current_path)
        except OSError:
            LOGGER.debug(
                "Unable to migrate legacy media entry from %s to %s",
                legacy_path,
                current_path,
                exc_info=True,
            )


def _migrate_legacy_rendition_dir(legacy_dir, current_dir):
    if not os.path.isdir(legacy_dir):
        return
    os.makedirs(current_dir, exist_ok=True)

    for entry in os.listdir(legacy_dir):
        legacy_path = os.path.join(legacy_dir, entry)
        current_path = os.path.join(current_dir, entry)

        if not os.path.isfile(legacy_path):
            continue
        if os.path.exists(current_path):
            try:
                os.remove(legacy_path)
            except OSError:
                LOGGER.debug("Unable to remove migrated legacy rendition: %s", legacy_path, exc_info=True)
            continue
        try:
            shutil.move(legacy_path, current_path)
        except OSError:
            LOGGER.debug(
                "Unable to migrate legacy rendition from %s to %s",
                legacy_path,
                current_path,
                exc_info=True,
            )

    try:
        if not os.listdir(legacy_dir):
            os.rmdir(legacy_dir)
    except OSError:
        LOGGER.debug("Unable to remove legacy rendition directory: %s", legacy_dir, exc_info=True)


def _migrate_current_media_root_to_original():
    media_root = C.STATIC_MEDIA_DIR
    if not os.path.isdir(media_root):
        return
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    skipped_names = {
        os.path.basename(UPLOAD_FOLDER),
        os.path.basename(VIDEO_THUMB_FOLDER),
        os.path.basename(IMAGE_VARIANT_FOLDER),
        os.path.basename(VIDEO_POSTER_FOLDER),
        os.path.basename(VIDEO_VARIANT_FOLDER),
        "visio-display.db",
        "config.json",
        "queue.json",
        "users.json",
    }

    for entry in os.listdir(media_root):
        if entry in skipped_names:
            continue
        source_path = os.path.join(media_root, entry)
        if not os.path.isfile(source_path):
            continue
        target_path = os.path.join(UPLOAD_FOLDER, entry)
        if os.path.exists(target_path):
            continue
        try:
            shutil.move(source_path, target_path)
        except OSError:
            LOGGER.debug(
                "Unable to migrate media root entry from %s to %s",
                source_path,
                target_path,
                exc_info=True,
            )


def harden_private_storage_permissions():
    private_dir = C.PRIVATE_DATA_DIR
    try:
        os.makedirs(private_dir, mode=0o700, exist_ok=True)
        os.chmod(private_dir, 0o700)
    except OSError:
        LOGGER.debug("Unable to harden private directory permissions: %s", private_dir, exc_info=True)


def require_database_url():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url
    raise RuntimeError(
        "DATABASE_URL is required. This project now runs in PostgreSQL-only mode "
        "and no longer falls back to SQLite."
    )


def _apply_additive_column_migration(table_name, column_definitions):
    try:
        inspector = inspect(db.engine)
        existing_columns = {
            column["name"]
            for column in inspector.get_columns(table_name)
        }
    except Exception:
        LOGGER.exception("Unable to inspect %s schema", table_name)
        return

    if not existing_columns:
        return
    changed = False
    for column_name, column_sql in column_definitions.items():
        if column_name in existing_columns:
            continue
        try:
            # SQL identifiers and column definitions cannot be bound as parameters.
            # Keep both fragments restricted to local migration definitions to avoid SQL injection.
            db.session.execute(
                text("ALTER TABLE " + table_name + " ADD COLUMN " + column_name + " " + column_sql)
            )
            changed = True
        except Exception:
            db.session.rollback()
            LOGGER.exception("Unable to add column %s to %s", column_name, table_name)
            return

    if changed:
        db.session.commit()


def migrate_database_schema():
    for migration in SCHEMA_MIGRATIONS:
        _apply_additive_column_migration(migration["table"], migration["columns"])


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def load_or_generate_secret_key():
    key_file = os.path.join(C.PRIVATE_DATA_DIR, "secret_key")
    if os.path.exists(key_file):
        with open(key_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    key = secrets.token_hex(32)
    with open(key_file, "w", encoding="utf-8") as handle:
        handle.write(key)
    os.chmod(key_file, 0o600)
    return key


def configure_app(app, *, max_batch_upload_size):
    app.secret_key = os.environ.get("SECRET_KEY") or load_or_generate_secret_key()
    app.config["MAX_CONTENT_LENGTH"] = max_batch_upload_size
    app.config["MAX_FORM_MEMORY_SIZE"] = max_batch_upload_size
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = env_flag("SESSION_COOKIE_SECURE")
    app.config["SESSION_COOKIE_NAME"] = os.environ.get("SESSION_COOKIE_NAME", "visio_session")
    app.config["SESSION_COOKIE_PATH"] = "/"
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        minutes=max(5, env_int("SESSION_LIFETIME_MINUTES", 480))
    )
    app.config["SESSION_REFRESH_EACH_REQUEST"] = False

    trusted_hosts = env_csv("TRUSTED_HOSTS")
    if trusted_hosts:
        app.config["TRUSTED_HOSTS"] = trusted_hosts

    app.config["SQLALCHEMY_DATABASE_URI"] = require_database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}


def configure_proxy(app):
    proxy_count = max(0, env_int("TRUST_PROXY_COUNT", 0))
    if not proxy_count:
        return
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=proxy_count,
        x_proto=proxy_count,
        x_host=proxy_count,
        x_port=proxy_count,
        x_prefix=proxy_count,
    )


def initialize_database(app):
    from services.search_index_svc import reseed_search_index
    db.init_app(app)
    with app.app_context():
        db.create_all()
        migrate_database_schema()
        reseed_search_index()
        init_users()
        init_rbac()
        harden_private_storage_permissions()


def register_blueprints(app):
    from blueprints.activity import bp as activity_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.api import bp as api_bp
    from blueprints.auth import bp as auth_bp
    from blueprints.campaigns import bp as campaigns_bp
    from blueprints.ephemeris import bp as ephemeris_bp
    from blueprints.media import bp as media_bp
    from blueprints.queue import bp as queue_bp
    from blueprints.roles import bp as roles_bp
    from blueprints.screens import bp as screens_bp
    from blueprints.search import bp as search_bp
    from blueprints.settings import bp as settings_bp
    from blueprints.version import bp as version_bp
    from blueprints.users import bp as users_bp
    from blueprints.wiki import bp as wiki_bp
    from blueprints.about import bp as about_bp

    for blueprint in (
        auth_bp,
        admin_bp,
        campaigns_bp,
        media_bp,
        screens_bp,
        queue_bp,
        ephemeris_bp,
        users_bp,
        settings_bp,
        version_bp,
        roles_bp,
        search_bp,
        api_bp,
        wiki_bp,
        about_bp,
        activity_bp,
    ):
        app.register_blueprint(blueprint)


def register_request_hooks(app):
    @app.before_request
    def protect_from_csrf():
        if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            return None
        if request.endpoint == "static":
            return None
        if request.endpoint == "auth.login":
            return None
        if request.endpoint == "api.api_client_heartbeat":
            return None

        provided = (
            request.headers.get("X-CSRF-Token")
            or request.form.get("_csrf_token")
            or (request.get_json(silent=True) or {}).get("_csrf_token")
        )
        if not provided or not secrets.compare_digest(str(provided), get_csrf_token()):
            abort(400, description="CSRF token missing or invalid")
        return None

    @app.after_request
    def apply_security_headers(response):
        csp = (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'self'; "
            "object-src 'none'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self' https://geocoding-api.open-meteo.com; "
            "media-src 'self' blob: data:; "
            "worker-src 'self' blob:"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault("Origin-Agent-Cluster", "?1")
        response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")

        cacheable_static = request.endpoint == "static" and request.path.startswith("/static/css/")
        if cacheable_static:
            response.headers["Cache-Control"] = "public, max-age=2592000, immutable"
            response.headers.pop("Pragma", None)
            response.headers.pop("Expires", None)

        sensitive_path = (
            request.path in {"/login", "/logout"}
            or request.path.startswith("/admin")
            or request.path.startswith("/api/config")
            or request.path.startswith("/api/activity")
            or request.path.startswith("/api/queue")
        )
        if sensitive_path and not cacheable_static:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.vary.add("Cookie")

        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


def register_error_handlers(app, *, max_file_upload_size, max_batch_upload_size):
    @app.errorhandler(413)
    def too_large(_error):
        content_length = request.content_length or 0
        error_code = "upload too large"
        if content_length > max_batch_upload_size:
            _flash("flash_batch_too_large", "error")
            error_code = "batch too large"
        elif content_length > max_file_upload_size:
            _flash("flash_file_too_large", "error")
            error_code = "file too large"
        else:
            _flash("flash_upload_too_large", "error")
        wants_json = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json"
        )
        if wants_json:
            return jsonify({"error": error_code}), 413
        return redirect(url_for("media.admin_upload_page")), 413


def register_template_context(app):
    @app.context_processor
    def inject_globals():
        lang = get_language()
        trans = _trans(lang)

        def t(key, **kwargs):
            value = trans.get(key, TRANSLATIONS["fr"].get(key, key))
            if kwargs:
                try:
                    value = value.format(**kwargs)
                except (KeyError, ValueError):
                    LOGGER.debug("Unable to format translation key: %s", key, exc_info=True)
            return value

        users = load_users()
        username = session.get("user")
        entry = users.get(username, {})
        user_theme = entry.get("theme", "violet") if isinstance(entry, dict) else "violet"
        cfg = load_config()
        default_screen_name = get_default_screen_name(cfg) or t("media_screen_default")
        translated_permissions = [(key, t(label_key)) for key, label_key in ALL_PERMISSIONS]
        from services.version_svc import _read_local_version

        static_version = _read_local_version() or "dev"
        admin_update_status = None
        if session.get("user") and request.path.startswith("/admin"):
            from services.version_svc import get_version_status

            admin_update_status = get_version_status(allow_remote=False)

        current_user_must_change_password = False
        if username:
            _u = get_user(username)
            current_user_must_change_password = bool(_u and _u.must_change_password)

        return dict(
            admin_update_status=admin_update_status,
            current_user_is_superadmin=is_superadmin(),
            current_user_must_change_password=current_user_must_change_password,
            has_permission=has_permission,
            is_feature_enabled=is_feature_enabled,
            theme=user_theme,
            app_name=cfg.get("app_name", "Helios"),
            lang=lang,
            static_version=static_version,
            repository_url=os.environ.get("APP_REPOSITORY_URL", "https://github.com/woofix/visio_display").strip(),
            t=t,
            all_permissions=translated_permissions,
            default_screen_name=default_screen_name,
            csrf_token=get_csrf_token,
        )


def register_public_routes(app):
    @app.route("/")
    def index():
        cfg = load_config()
        screen = request.args.get("screen", "").strip().lower()
        halo_color = get_screen_halo_color(screen, cfg)
        return render_template(
            "index.html",
            display_halo_color=halo_color,
            display_halo_rgb=halo_color_to_rgb(halo_color),
        )
