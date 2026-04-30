# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from datetime import datetime, UTC
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from constants import ALL_PERMISSIONS
from services.activity_svc import log_config_change
from services.rbac_svc import get_all_roles, set_user_roles
from services.users_svc import (
    create_user,
    delete_user_account,
    get_user,
    is_admin,
    is_valid_password,
    is_valid_username,
    load_users,
    normalize_username,
    set_must_change_password,
    set_user_password,
    update_user_permissions,
    update_user_screens,
    user_exists,
    verify_user_password,
)
from services.config_svc import load_config, save_config
from services.media_svc import get_logo_path
from services.i18n import _flash, _t
from blueprints.guards import superadmin_guard, feature_guard_json

bp = Blueprint('users', __name__)


@bp.route('/admin/superadmin')
def admin_superadmin_page():
    g = superadmin_guard()
    if g: return g
    return redirect('/admin/settings/administration')


@bp.route('/admin/users')
def admin_users_page():
    g = superadmin_guard()
    if g: return g
    return redirect('/admin/settings/comptes-permissions')


@bp.route('/admin/users/add', methods=['GET'])
@bp.route('/admin/users/create', methods=['GET'])
@bp.route('/admin/users/new', methods=['GET'])
def admin_add_user_page():
    g = superadmin_guard()
    if g: return g
    return redirect('/admin/settings/ajouter-compte')


@bp.route('/admin/users/add', methods=['POST'])
@bp.route('/admin/users/create', methods=['POST'])
@bp.route('/admin/users', methods=['POST'])
def add_user():
    g = superadmin_guard()
    if g: return g
    username = normalize_username(request.form.get('username', ''))
    password = request.form.get('password', '').strip()
    if not username or not password:
        _flash('flash_user_pass_required', 'error')
        return redirect('/admin/settings/ajouter-compte')
    if not is_valid_username(username):
        _flash('flash_invalid_username', 'error')
        return redirect('/admin/settings/ajouter-compte')
    if not is_valid_password(password):
        _flash('flash_password_too_short', 'error')
        return redirect('/admin/settings/ajouter-compte')
    if user_exists(username):
        _flash('flash_user_exists', 'error', username=username)
        return redirect('/admin/settings/ajouter-compte')
    create_user(username, password, superadmin=False, permissions=[])
    role_id = request.form.get('role_id', '').strip()
    if role_id.isdigit():
        set_user_roles(username, [int(role_id)])
    log_config_change(session.get('user'), f'user created:{username}')
    _flash('flash_user_created', 'success', username=username)
    return redirect('/admin/settings/comptes-permissions')


@bp.route('/admin/users/delete/<username>', methods=['POST'])
def delete_user(username):
    g = superadmin_guard()
    if g: return g
    user = get_user(username)
    if user is not None and user.superadmin:
        _flash('flash_cannot_delete_superadmin', 'error')
        return redirect('/admin/settings/comptes-permissions')
    if user is None:
        _flash('flash_user_not_found', 'error')
        return redirect('/admin/settings/comptes-permissions')
    delete_user_account(username)
    log_config_change(session.get('user'), f'user deleted:{username}')
    _flash('flash_user_deleted', 'success', username=username)
    return redirect('/admin/settings/comptes-permissions')


@bp.route('/admin/users/password', methods=['POST'])
def change_password():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    current  = request.form.get('current_password', '')
    new_pwd  = request.form.get('new_password', '').strip()
    username = session.get('user')
    if not verify_user_password(username, current):
        _flash('flash_wrong_password', 'error')
        return redirect('/admin/settings/mot-de-passe')
    if not is_valid_password(new_pwd):
        _flash('flash_new_password_too_short', 'error')
        return redirect('/admin/settings/mot-de-passe')
    set_user_password(username, new_pwd)
    set_must_change_password(username, False)
    log_config_change(username, 'password changed')
    _flash('flash_password_updated', 'success')
    return redirect('/admin/settings/mot-de-passe')


@bp.route('/admin/users/reset_password/<username>', methods=['POST'])
def reset_user_password(username):
    return _reset_user_password_for(username)


@bp.route('/admin/users/reset_password', methods=['POST'])
def reset_selected_user_password():
    return _reset_user_password_for(request.form.get('username', ''))


def _reset_user_password_for(username):
    g = superadmin_guard()
    if g: return g
    username = normalize_username(username)
    user = get_user(username)
    if user is None:
        _flash('flash_user_not_found', 'error')
        return redirect('/admin/settings/comptes-permissions')
    new_pwd = request.form.get('new_password', '').strip()
    if not is_valid_password(new_pwd):
        _flash('flash_new_password_too_short', 'error')
        return redirect('/admin/settings/comptes-permissions')
    set_user_password(username, new_pwd)
    set_must_change_password(username, True)
    log_config_change(session.get('user'), f'password reset:{username}')
    _flash('flash_user_password_reset', 'success', username=username)
    return redirect('/admin/settings/comptes-permissions')


@bp.route('/admin/users/permissions/<username>', methods=['POST'])
def set_permissions(username):
    g = superadmin_guard()
    if g: return g
    user = get_user(username)
    if user is None:
        _flash('flash_user_not_found', 'error')
        return redirect('/admin/settings/comptes-permissions')
    if user.superadmin:
        _flash('flash_superadmin_perms_locked', 'error')
        return redirect('/admin/settings/comptes-permissions')
    perms = [p for p, _ in ALL_PERMISSIONS if request.form.get(f'perm_{p}')]
    update_user_permissions(username, perms)
    log_config_change(session.get('user'), f'permissions {username}: {", ".join(perms) if perms else "none"}')
    _flash('flash_permissions_updated', 'success', username=username)
    return redirect('/admin/settings/comptes-permissions')


@bp.route('/admin/users/screens/<username>', methods=['POST'])
def set_user_screens(username):
    g = superadmin_guard()
    if g: return g
    user = get_user(username)
    if user is None:
        _flash('flash_user_not_found', 'error')
        return redirect('/admin/settings/comptes-permissions')
    if user.superadmin:
        _flash('flash_superadmin_perms_locked', 'error')
        return redirect('/admin/settings/comptes-permissions')
    cfg         = load_config()
    all_screens = ['', *cfg.get('screens', {}).keys()]
    selected    = [s for s in all_screens if request.form.get(f'screen_{s}')]
    update_user_screens(username, selected)
    log_config_change(session.get('user'), f'screens {username}: {", ".join(selected) if selected else "all"}')
    _flash('flash_screens_updated', 'success', username=username)
    return redirect('/admin/settings/comptes-permissions')


@bp.route('/admin/priority-alert', methods=['POST'])
def set_priority_alert():
    g = superadmin_guard()
    if g: return g
    g = feature_guard_json('priority_alert')
    if g: return g

    message = request.form.get('message', '')
    message = ' '.join(message.split())[:280]

    cfg = load_config()
    cfg['priority_alert'] = {
        'message': message,
        'updated_at': datetime.now(UTC).isoformat(timespec='seconds'),
    }
    save_config(cfg)
    detail = 'priority alert cleared' if not message else f'priority alert:{message}'
    log_config_change(session.get('user'), detail)

    return jsonify({
        'ok': True,
        'message': message,
        'updated_at': cfg['priority_alert']['updated_at'],
    })
