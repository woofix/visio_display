# MIT License - Copyright (c) 2026 Lycée Sainte Louise de Marillac
# See LICENSE file for details

import json
import os
import secrets
import shutil
from datetime import timedelta
from flask import Flask, abort, request
from werkzeug.middleware.proxy_fix import ProxyFix

from constants import (
    ALL_PERMISSIONS, DB_FILE, CONFIG_FILE, QUEUE_FILE, USERS_FILE,
    LEGACY_DB_FILE, LEGACY_CONFIG_FILE, LEGACY_QUEUE_FILE, LEGACY_USERS_FILE,
)
from db import db, AppConfig, User, EncodeJob
from services.users_svc import init_users
from services.queue_svc import start_encoder_thread
from services.i18n import get_language, _trans
from services.users_svc import load_users, is_superadmin, has_permission
from services.config_svc import load_config, is_feature_enabled, get_default_screen_name
from flask import session
from translations import TRANSLATIONS


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_int(name, default):
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_csv(name):
    raw = os.environ.get(name, '')
    return [item.strip() for item in raw.split(',') if item.strip()]


def _migrate_legacy_storage():
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


def _harden_private_storage_permissions():
    private_dir = os.path.dirname(DB_FILE)
    try:
        os.makedirs(private_dir, mode=0o700, exist_ok=True)
        os.chmod(private_dir, 0o700)
    except OSError:
        pass

    for path in (DB_FILE, CONFIG_FILE, QUEUE_FILE, USERS_FILE):
        if not os.path.exists(path):
            continue
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def _migrate_from_json():
    try:
        if AppConfig.query.count() == 0:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE) as f:
                    data = f.read()
            else:
                data = json.dumps({"order": [], "durations": {}, "disabled": []})
            db.session.add(AppConfig(id=1, data=data))
            db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        if User.query.count() == 0 and os.path.exists(USERS_FILE):
            with open(USERS_FILE) as f:
                users_dict = json.load(f)
            for username, entry in users_dict.items():
                db.session.merge(User.from_dict(username, entry))
            db.session.commit()
    except Exception:
        db.session.rollback()

    try:
        if EncodeJob.query.count() == 0 and os.path.exists(QUEUE_FILE):
            with open(QUEUE_FILE) as f:
                jobs = json.load(f)
            for job in jobs:
                db.session.merge(EncodeJob(
                    id=job['id'],
                    filename=job['filename'],
                    status=job['status'],
                    added=job['added'],
                    started=job.get('started'),
                    finished=job.get('finished'),
                    new_name=job.get('new_name'),
                    before_mb=job.get('before'),
                    after_mb=job.get('after'),
                    ratio=job.get('ratio'),
                    message=job.get('message'),
                ))
            db.session.commit()
    except Exception:
        db.session.rollback()


def _get_csrf_token():
    token = session.get('_csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['_csrf_token'] = token
    return token


def create_app(start_scheduler=True, test_config=None):
    _migrate_legacy_storage()
    _harden_private_storage_permissions()
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY')
    if not app.secret_key:
        raise RuntimeError("La variable d'environnement SECRET_KEY est obligatoire.")
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 Mo
    app.config['MAX_FORM_MEMORY_SIZE'] = 16 * 1024 * 1024
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = _env_flag('SESSION_COOKIE_SECURE')
    app.config['SESSION_COOKIE_NAME'] = os.environ.get('SESSION_COOKIE_NAME', 'visio_session')
    app.config['SESSION_COOKIE_PATH'] = '/'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
        minutes=max(5, _env_int('SESSION_LIFETIME_MINUTES', 480))
    )
    app.config['SESSION_REFRESH_EACH_REQUEST'] = False
    trusted_hosts = _env_csv('TRUSTED_HOSTS')
    if trusted_hosts:
        app.config['TRUSTED_HOSTS'] = trusted_hosts

    # SQLAlchemy
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.abspath(DB_FILE)}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'check_same_thread': False},
    }

    if test_config:
        app.config.update(test_config)

    proxy_count = max(0, _env_int('TRUST_PROXY_COUNT', 0))
    if proxy_count:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_count,
            x_proto=proxy_count,
            x_host=proxy_count,
            x_port=proxy_count,
            x_prefix=proxy_count,
        )

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _migrate_from_json()
        init_users()
        _harden_private_storage_permissions()

    # Blueprints
    from blueprints.auth      import bp as auth_bp
    from blueprints.admin     import bp as admin_bp
    from blueprints.media     import bp as media_bp
    from blueprints.screens   import bp as screens_bp
    from blueprints.queue     import bp as queue_bp
    from blueprints.ephemeris import bp as ephemeris_bp
    from blueprints.users     import bp as users_bp
    from blueprints.settings  import bp as settings_bp
    from blueprints.api       import bp as api_bp
    from blueprints.wiki      import bp as wiki_bp
    from blueprints.activity  import bp as activity_bp

    for bp in (auth_bp, admin_bp, media_bp, screens_bp, queue_bp,
               ephemeris_bp, users_bp, settings_bp, api_bp, wiki_bp, activity_bp):
        app.register_blueprint(bp)

    @app.before_request
    def protect_from_csrf():
        if request.method in {'GET', 'HEAD', 'OPTIONS', 'TRACE'}:
            return None
        if request.endpoint == 'static':
            return None
        if request.endpoint == 'auth.login':
            return None
        if request.endpoint == 'api.api_client_heartbeat':
            return None
        provided = (
            request.headers.get('X-CSRF-Token')
            or request.form.get('_csrf_token')
            or (request.get_json(silent=True) or {}).get('_csrf_token')
        )
        if not provided or not secrets.compare_digest(str(provided), _get_csrf_token()):
            abort(400, description='CSRF token missing or invalid')
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
        response.headers.setdefault('Content-Security-Policy', csp)
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Permissions-Policy', 'camera=(), geolocation=(), microphone=()')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault('Cross-Origin-Resource-Policy', 'same-origin')
        response.headers.setdefault('Origin-Agent-Cluster', '?1')
        response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')

        sensitive_path = (
            request.path in {'/login', '/logout'}
            or request.path.startswith('/admin')
            or request.path.startswith('/api/config')
            or request.path.startswith('/api/activity')
            or request.path.startswith('/api/queue')
        )
        if session.get('user') or sensitive_path:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            response.vary.add('Cookie')

        if request.is_secure:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    @app.errorhandler(413)
    def too_large(e):
        from services.i18n import _flash
        from flask import redirect, url_for
        _flash('flash_file_too_large', 'error')
        return redirect(url_for('media.admin_upload_page')), 413

    @app.context_processor
    def inject_globals():
        lang  = get_language()
        trans = _trans(lang)

        def t(key, **kwargs):
            val = trans.get(key, TRANSLATIONS['fr'].get(key, key))
            if kwargs:
                try:
                    val = val.format(**kwargs)
                except (KeyError, ValueError):
                    pass
            return val

        users    = load_users()
        username = session.get('user')
        entry    = users.get(username, {})
        user_theme = entry.get('theme', 'violet') if isinstance(entry, dict) else 'violet'
        cfg = load_config()
        default_screen_name = get_default_screen_name(cfg) or t('media_screen_default')

        translated_permissions = [(k, t(lbl_key)) for k, lbl_key in ALL_PERMISSIONS]

        return dict(
            current_user_is_superadmin=is_superadmin(),
            has_permission=has_permission,
            is_feature_enabled=is_feature_enabled,
            theme=user_theme,
            app_name=cfg.get('app_name', 'Helios'),
            lang=lang,
            t=t,
            all_permissions=translated_permissions,
            default_screen_name=default_screen_name,
            csrf_token=_get_csrf_token,
        )

    if start_scheduler:
        start_encoder_thread(app)

    return app


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=8080)
