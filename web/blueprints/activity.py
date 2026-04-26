# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for

from services.activity_svc import (
    apply_activity_retention_now,
    get_activity_log,
    get_activity_settings,
    get_activity_summary,
    purge_activity_log,
)
from services.config_svc import load_config, save_config
from services.i18n import _flash
from services.media_svc import get_logo_path
from services.users_svc import load_users, is_superadmin
from blueprints.guards import admin_guard, feature_guard, superadmin_guard
from services.activity_svc import log_config_change

bp = Blueprint('activity', __name__)


@bp.route('/admin/activity')
def activity_page():
    redir = admin_guard()
    if redir: return redir
    redir = feature_guard('activity')
    if redir: return redir
    logs = get_activity_log(limit=1000)
    users = load_users()
    known_users = sorted({*users.keys(), *(entry['username'] for entry in logs if entry.get('username'))})
    return render_template('admin_activity.html',
        logs=logs,
        users=known_users,
        current_user=session.get('user'),
        is_superadmin=is_superadmin(),
        activity_settings=get_activity_settings(),
        activity_summary=get_activity_summary(),
        logo_path=get_logo_path())


@bp.route('/api/activity')
def api_activity():
    redir = admin_guard()
    if redir: return jsonify({"error": "unauthorized"}), 401
    try:
        limit = min(int(request.args.get('limit', 200)), 1000)
    except (TypeError, ValueError):
        limit = 200
    return jsonify(get_activity_log(limit=limit))


@bp.route('/admin/activity/settings', methods=['POST'])
def update_activity_settings():
    redir = superadmin_guard()
    if redir: return redir
    redir = feature_guard('activity')
    if redir: return redir

    try:
        retention_days = max(1, int(request.form.get('retention_days', '0')))
        max_rows = max(1000, int(request.form.get('max_rows', '0')))
    except (TypeError, ValueError):
        _flash('flash_activity_settings_invalid', 'error')
        return redirect(url_for('activity.activity_page'))

    cfg = load_config()
    cfg['activity_log'] = {
        'auto_delete_enabled': bool(request.form.get('auto_delete_enabled')),
        'retention_days': retention_days,
        'max_rows': max_rows,
    }
    save_config(cfg)
    deleted = apply_activity_retention_now()
    log_config_change(
        session.get('user'),
        (
            'journal activité: '
            f"suppression_auto={'oui' if cfg['activity_log']['auto_delete_enabled'] else 'non'}, "
            f"conservation={retention_days}j, limite={max_rows}, purge={deleted}"
        ),
    )
    _flash('flash_activity_settings_saved', 'success')
    return redirect(url_for('activity.activity_page'))


@bp.route('/admin/activity/purge', methods=['POST'])
def purge_activity():
    redir = superadmin_guard()
    if redir: return redir
    redir = feature_guard('activity')
    if redir: return redir

    purge_scope = (request.form.get('purge_scope') or '').strip()
    if purge_scope == 'older_than':
        try:
            older_than_days = max(1, int(request.form.get('older_than_days', '0')))
        except (TypeError, ValueError):
            _flash('flash_activity_purge_invalid', 'error')
            return redirect(url_for('activity.activity_page'))
        deleted = purge_activity_log(older_than_days=older_than_days)
        log_config_change(session.get('user'), f'journal activité purgé: plus de {older_than_days} jours ({deleted} entrées)')
    elif purge_scope == 'all':
        deleted = purge_activity_log()
        log_config_change(session.get('user'), f'journal activité purgé intégralement ({deleted} entrées)')
    else:
        _flash('flash_activity_purge_invalid', 'error')
        return redirect(url_for('activity.activity_page'))

    _flash('flash_activity_purged', 'success')
    return redirect(url_for('activity.activity_page'))
