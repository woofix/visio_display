# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Flask

import constants as C
from app_bootstrap import (
    configure_app,
    configure_proxy,
    harden_private_storage_permissions,
    initialize_database,
    migrate_legacy_storage,
    register_blueprints,
    register_error_handlers,
    register_public_routes,
    register_request_hooks,
    register_template_context,
    schedule_initial_ephemeris_refresh,
)
from services.queue_svc import start_encoder_thread

MAX_FILE_UPLOAD_SIZE = getattr(C, 'MAX_FILE_UPLOAD_SIZE', 150 * 1024 * 1024)
MAX_BATCH_UPLOAD_SIZE = getattr(C, 'MAX_BATCH_UPLOAD_SIZE', 256 * 1024 * 1024)
def create_app(start_scheduler=True, test_config=None):
    migrate_legacy_storage()
    harden_private_storage_permissions()
    app = Flask(__name__)
    configure_app(app, max_batch_upload_size=MAX_BATCH_UPLOAD_SIZE)

    if test_config:
        app.config.update(test_config)

    configure_proxy(app)
    initialize_database(app)
    register_blueprints(app)
    register_request_hooks(app)
    register_error_handlers(
        app,
        max_file_upload_size=MAX_FILE_UPLOAD_SIZE,
        max_batch_upload_size=MAX_BATCH_UPLOAD_SIZE,
    )
    register_template_context(app)
    register_public_routes(app)

    if start_scheduler:
        start_encoder_thread(app)
        with app.app_context():
            schedule_initial_ephemeris_refresh()

    return app


if __name__ == '__main__':
    create_app().run(host='0.0.0.0', port=8080)
