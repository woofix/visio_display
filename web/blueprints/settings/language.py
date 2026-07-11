# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import redirect, request, session

from blueprints.guards import admin_guard
from services.activity_svc import log_config_change
from services.i18n import _flash
from services.settings_sections import settings_section_url
from services.users_svc import update_user_language

from . import bp


@bp.route('/admin/settings/language', methods=['POST'])
def set_language():
    redir = admin_guard()
    if redir: return redir
    lang = request.form.get('language', 'fr')
    if lang not in ('fr', 'en'):
        lang = 'fr'
    username = session.get('user')
    if username:
        update_user_language(username, lang)
        log_config_change(username, f'langue:{lang}')
        from services.ephemeris_svc import ensure_ephemeride_image_async
        ensure_ephemeride_image_async(force=True)
    _flash('flash_language_updated', 'success')
    return redirect(settings_section_url('language'))
