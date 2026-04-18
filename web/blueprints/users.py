from flask import Blueprint, request, redirect, url_for, session, render_template, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, UTC

from constants import ALL_PERMISSIONS
from services.users_svc import load_users, save_users, is_admin
from services.config_svc import load_config, save_config
from services.media_svc import get_logo_path
from services.i18n import _flash, _t
from blueprints.guards import superadmin_guard

bp = Blueprint('users', __name__)


@bp.route('/admin/superadmin')
def admin_superadmin_page():
    g = superadmin_guard()
    if g: return g
    users = load_users()
    cfg   = load_config()
    return render_template('admin_superadmin.html',
        users=users,
        all_permissions=[(k, _t(lbl_key)) for k, lbl_key in ALL_PERMISSIONS],
        all_screens=list(cfg.get('screens', {}).keys()),
        priority_alert=cfg.get('priority_alert', {}),
        current_user=session.get('user'),
        logo_path=get_logo_path())


@bp.route('/admin/users/add', methods=['POST'])
def add_user():
    g = superadmin_guard()
    if g: return g
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    if not username or not password:
        _flash('flash_user_pass_required', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    if len(password) < 8:
        _flash('flash_password_too_short', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    users = load_users()
    if username in users:
        _flash('flash_user_exists', 'error', username=username)
        return redirect(url_for('users.admin_superadmin_page'))
    users[username] = {"password": generate_password_hash(password),
                       "superadmin": False,
                       "permissions": []}
    save_users(users)
    _flash('flash_user_created', 'success', username=username)
    return redirect(url_for('users.admin_superadmin_page'))


@bp.route('/admin/users/delete/<username>', methods=['POST'])
def delete_user(username):
    g = superadmin_guard()
    if g: return g
    users = load_users()
    superadmins = [u for u, e in users.items() if isinstance(e, dict) and e.get('superadmin')]
    if username in superadmins:
        _flash('flash_cannot_delete_superadmin', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    if username not in users:
        _flash('flash_user_not_found', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    del users[username]
    save_users(users)
    _flash('flash_user_deleted', 'success', username=username)
    return redirect(url_for('users.admin_superadmin_page'))


@bp.route('/admin/users/password', methods=['POST'])
def change_password():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    current  = request.form.get('current_password', '')
    new_pwd  = request.form.get('new_password', '').strip()
    username = session.get('user')
    users    = load_users()
    entry    = users.get(username, {})
    pwd_hash = entry.get('password', '') if isinstance(entry, dict) else entry
    if not check_password_hash(pwd_hash, current):
        _flash('flash_wrong_password', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=admins')
    if len(new_pwd) < 8:
        _flash('flash_new_password_too_short', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=admins')
    users[username]['password'] = generate_password_hash(new_pwd)
    save_users(users)
    _flash('flash_password_updated', 'success')
    return redirect(url_for('settings.admin_settings_page') + '?tab=admins')


@bp.route('/admin/users/reset_password/<username>', methods=['POST'])
def reset_user_password(username):
    g = superadmin_guard()
    if g: return g
    users = load_users()
    if username not in users:
        _flash('flash_user_not_found', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    new_pwd = request.form.get('new_password', '').strip()
    if len(new_pwd) < 8:
        _flash('flash_new_password_too_short', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    users[username]['password'] = generate_password_hash(new_pwd)
    save_users(users)
    _flash('flash_user_password_reset', 'success', username=username)
    return redirect(url_for('users.admin_superadmin_page'))


@bp.route('/admin/users/permissions/<username>', methods=['POST'])
def set_permissions(username):
    g = superadmin_guard()
    if g: return g
    users = load_users()
    if username not in users:
        _flash('flash_user_not_found', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    entry = users[username]
    if isinstance(entry, dict) and entry.get('superadmin'):
        _flash('flash_superadmin_perms_locked', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    perms = [p for p, _ in ALL_PERMISSIONS if request.form.get(f'perm_{p}')]
    users[username]['permissions'] = perms
    save_users(users)
    _flash('flash_permissions_updated', 'success', username=username)
    return redirect(url_for('users.admin_superadmin_page'))


@bp.route('/admin/users/screens/<username>', methods=['POST'])
def set_user_screens(username):
    g = superadmin_guard()
    if g: return g
    users = load_users()
    if username not in users:
        _flash('flash_user_not_found', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    entry = users[username]
    if isinstance(entry, dict) and entry.get('superadmin'):
        _flash('flash_superadmin_perms_locked', 'error')
        return redirect(url_for('users.admin_superadmin_page'))
    cfg         = load_config()
    all_screens = list(cfg.get('screens', {}).keys())
    selected    = [s for s in all_screens if request.form.get(f'screen_{s}')]
    users[username]['screens'] = selected if selected else None
    save_users(users)
    _flash('flash_screens_updated', 'success', username=username)
    return redirect(url_for('users.admin_superadmin_page'))


@bp.route('/admin/priority-alert', methods=['POST'])
def set_priority_alert():
    g = superadmin_guard()
    if g: return g

    message = request.form.get('message', '')
    message = ' '.join(message.split())[:280]

    cfg = load_config()
    cfg['priority_alert'] = {
        'message': message,
        'updated_at': datetime.now(UTC).isoformat(timespec='seconds'),
    }
    save_config(cfg)

    return jsonify({
        'ok': True,
        'message': message,
        'updated_at': cfg['priority_alert']['updated_at'],
    })
