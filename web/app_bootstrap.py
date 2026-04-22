# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import json
import logging
import os
import secrets
import shutil
from datetime import timedelta

from flask import abort, redirect, render_template, request, session, url_for
from sqlalchemy import inspect, text
from werkzeug.middleware.proxy_fix import ProxyFix

import constants as C
from constants import (
    ALL_PERMISSIONS,
    CONFIG_FILE,
    DB_FILE,
    LEGACY_CONFIG_FILE,
    LEGACY_DB_FILE,
    LEGACY_QUEUE_FILE,
    LEGACY_USERS_FILE,
    QUEUE_FILE,
    USERS_FILE,
)
from db import AppConfig, EncodeJob, User, db
from services.config_svc import get_default_screen_name, is_feature_enabled, load_config
from services.i18n import _flash, _trans, get_language
from services.users_svc import has_permission, init_users, is_superadmin, load_users
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
    for legacy, current in (
        (LEGACY_DB_FILE, DB_FILE),
        (LEGACY_CONFIG_FILE, CONFIG_FILE),
        (LEGACY_QUEUE_FILE, QUEUE_FILE),
        (LEGACY_USERS_FILE, USERS_FILE),
    ):
        if os.path.exists(current) or not os.path.exists(legacy):
            continue
        os.makedirs(os.path.dirname(current), exist_ok=True)
        shutil.move(legacy, current)


def harden_private_storage_permissions():
    private_dir = os.path.dirname(DB_FILE)
    try:
        os.makedirs(private_dir, mode=0o700, exist_ok=True)
        os.chmod(private_dir, 0o700)
    except OSError:
        LOGGER.debug("Unable to harden private directory permissions: %s", private_dir, exc_info=True)

    for path in (DB_FILE, CONFIG_FILE, QUEUE_FILE, USERS_FILE):
        if not os.path.exists(path):
            continue
        try:
            os.chmod(path, 0o600)
        except OSError:
            LOGGER.debug("Unable to harden file permissions: %s", path, exc_info=True)


def migrate_from_json():
    try:
        if AppConfig.query.count() == 0:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, encoding="utf-8") as handle:
                    data = handle.read()
            else:
                data = json.dumps({"order": [], "durations": {}, "disabled": []})
            db.session.add(AppConfig(id=1, data=data))
            db.session.commit()
    except Exception:
        db.session.rollback()
        LOGGER.exception("Unable to migrate config.json into database")

    try:
        if User.query.count() == 0 and os.path.exists(USERS_FILE):
            with open(USERS_FILE, encoding="utf-8") as handle:
                users_dict = json.load(handle)
            from services.users_svc import PASSWORD_HASH_PLACEHOLDER, set_user_password_hash

            for username, entry in users_dict.items():
                row = User.from_dict(username, entry)
                merged = db.session.merge(row)
                if isinstance(entry, dict):
                    password_hash = entry.get("password", "")
                else:
                    password_hash = entry
                if password_hash:
                    set_user_password_hash(username, password_hash)
                merged.password_hash = PASSWORD_HASH_PLACEHOLDER
            db.session.commit()
    except Exception:
        db.session.rollback()
        LOGGER.exception("Unable to migrate users.json into database")

    try:
        if EncodeJob.query.count() == 0 and os.path.exists(QUEUE_FILE):
            with open(QUEUE_FILE, encoding="utf-8") as handle:
                jobs = json.load(handle)
            for job in jobs:
                db.session.merge(
                    EncodeJob(
                        id=job["id"],
                        filename=job["filename"],
                        status=job["status"],
                        added=job["added"],
                        started=job.get("started"),
                        finished=job.get("finished"),
                        new_name=job.get("new_name"),
                        before_mb=job.get("before"),
                        after_mb=job.get("after"),
                        ratio=job.get("ratio"),
                        message=job.get("message"),
                    )
                )
            db.session.commit()
    except Exception:
        db.session.rollback()
        LOGGER.exception("Unable to migrate queue.json into database")


def migrate_client_heartbeats_schema():
    try:
        inspector = inspect(db.engine)
        existing_columns = {
            column["name"]
            for column in inspector.get_columns("client_heartbeats")
        }
    except Exception:
        LOGGER.exception("Unable to inspect client_heartbeats schema")
        return

    if not existing_columns:
        return
    changed = False
    for column_name, column_sql in CLIENT_HEARTBEAT_EXTRA_COLUMNS.items():
        if column_name in existing_columns:
            continue
        try:
            db.session.execute(
                text(f"ALTER TABLE client_heartbeats ADD COLUMN {column_name} {column_sql}")
            )
            changed = True
        except Exception:
            db.session.rollback()
            LOGGER.exception("Unable to add column %s to client_heartbeats", column_name)
            return

    if changed:
        db.session.commit()


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

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.abspath(DB_FILE)}",
    )
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
    db.init_app(app)
    with app.app_context():
        db.create_all()
        migrate_client_heartbeats_schema()
        migrate_from_json()
        init_users()
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
    from blueprints.screens import bp as screens_bp
    from blueprints.settings import bp as settings_bp
    from blueprints.users import bp as users_bp
    from blueprints.wiki import bp as wiki_bp

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
        api_bp,
        wiki_bp,
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
            "font-src 'self' https://fonts.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
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

        sensitive_path = (
            request.path in {"/login", "/logout"}
            or request.path.startswith("/admin")
            or request.path.startswith("/api/config")
            or request.path.startswith("/api/activity")
            or request.path.startswith("/api/queue")
        )
        if session.get("user") or sensitive_path:
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
        if content_length > max_batch_upload_size:
            _flash("flash_batch_too_large", "error")
        elif content_length > max_file_upload_size:
            _flash("flash_file_too_large", "error")
        else:
            _flash("flash_upload_too_large", "error")
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

        return dict(
            current_user_is_superadmin=is_superadmin(),
            has_permission=has_permission,
            is_feature_enabled=is_feature_enabled,
            theme=user_theme,
            app_name=cfg.get("app_name", "Helios"),
            lang=lang,
            t=t,
            all_permissions=translated_permissions,
            default_screen_name=default_screen_name,
            csrf_token=get_csrf_token,
        )


def register_public_routes(app):
    @app.route("/")
    def index():
        return render_template("index.html")
