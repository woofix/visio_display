# MIT License - Copyright (c) 2026 Lycée Sainte Louise de Marillac
# See LICENSE file for details

import json
import os
from flask import Flask

from constants import ALL_PERMISSIONS, ALL_FEATURES, DB_FILE, CONFIG_FILE, QUEUE_FILE, USERS_FILE
from db import db, AppConfig, User, EncodeJob
from services.users_svc import init_users
from services.queue_svc import start_encoder_thread
from services.i18n import get_language, _trans
from services.users_svc import load_users, is_superadmin, has_permission
from services.config_svc import load_config, is_feature_enabled
from flask import session
from translations import TRANSLATIONS


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


def create_app(start_scheduler=True, test_config=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY')
    if not app.secret_key:
        raise RuntimeError("La variable d'environnement SECRET_KEY est obligatoire.")
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 Mo

    # SQLAlchemy
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.abspath(DB_FILE)}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'check_same_thread': False},
    }

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    with app.app_context():
        db.create_all()
        _migrate_from_json()
        init_users()

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
        )

    if start_scheduler:
        start_encoder_thread(app)

    return app


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=8080)
