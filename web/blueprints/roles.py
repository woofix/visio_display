# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, jsonify, redirect, render_template, request, session

from constants import ALL_PERMISSIONS
from services.activity_svc import log_config_change
from services.rbac_svc import (
    create_role,
    delete_role,
    get_all_roles,
    get_user_roles,
    is_valid_role_name,
    set_role_permissions,
    set_user_roles,
    update_role,
)
from services.users_svc import get_user, is_valid_username, load_users
from services.i18n import _flash
from blueprints.guards import superadmin_guard

bp = Blueprint('roles', __name__)

_REDIRECT = '/admin/roles'


@bp.route('/admin/roles')
def admin_roles_page():
    g = superadmin_guard()
    if g:
        return g
    roles = get_all_roles()
    all_users = load_users()
    users = {u: get_user_roles(u) for u in all_users.keys()}
    users_sa = {u: bool(d.get('superadmin', False)) for u, d in all_users.items()}
    return render_template(
        'admin_roles.html',
        roles=roles,
        all_permissions=ALL_PERMISSIONS,
        users_roles=users,
        users_sa=users_sa,
        current_user=session.get('user'),
    )


@bp.route('/admin/roles/create', methods=['POST'])
def create_role_route():
    g = superadmin_guard()
    if g:
        return g
    name         = request.form.get('name', '').strip().lower()
    display_name = request.form.get('display_name', '').strip()
    description  = request.form.get('description', '').strip()
    permissions  = [p for p, _ in ALL_PERMISSIONS if request.form.get(f'perm_{p}')]
    if not name or not display_name:
        _flash('flash_role_name_required', 'error')
        return redirect(_REDIRECT)
    if not is_valid_role_name(name):
        _flash('flash_role_name_invalid', 'error')
        return redirect(_REDIRECT)
    try:
        role = create_role(name, display_name, description, permissions)
        log_config_change(session.get('user'), f'rôle créé: {role.name}')
        _flash('flash_role_created', 'success', name=role.display_name)
    except ValueError as exc:
        _flash(str(exc), 'error')
    return redirect(_REDIRECT)


@bp.route('/admin/roles/<int:role_id>/edit', methods=['POST'])
def edit_role_route(role_id):
    g = superadmin_guard()
    if g:
        return g
    display_name = request.form.get('display_name', '').strip()
    description  = request.form.get('description', '').strip()
    if not display_name:
        _flash('flash_role_name_required', 'error')
        return redirect(_REDIRECT)
    try:
        role = update_role(role_id, display_name, description)
        log_config_change(session.get('user'), f'rôle modifié: {role.name}')
        _flash('flash_role_updated', 'success', name=role.display_name)
    except ValueError as exc:
        _flash(str(exc), 'error')
    return redirect(_REDIRECT)


@bp.route('/admin/roles/<int:role_id>/permissions', methods=['POST'])
def set_role_permissions_route(role_id):
    g = superadmin_guard()
    if g:
        return g
    permissions = [p for p, _ in ALL_PERMISSIONS if request.form.get(f'perm_{p}')]
    try:
        set_role_permissions(role_id, permissions)
        from services.rbac_svc import get_role
        role = get_role(role_id)
        log_config_change(session.get('user'), f'permissions rôle {role.name}: {", ".join(permissions) or "aucune"}')
        _flash('flash_role_perms_updated', 'success', name=role.display_name)
    except ValueError as exc:
        _flash(str(exc), 'error')
    return redirect(_REDIRECT)


@bp.route('/admin/roles/<int:role_id>/delete', methods=['POST'])
def delete_role_route(role_id):
    g = superadmin_guard()
    if g:
        return g
    try:
        from services.rbac_svc import get_role
        role = get_role(role_id)
        if role is None:
            _flash('flash_role_not_found', 'error')
            return redirect(_REDIRECT)
        role_name = role.display_name
        delete_role(role_id)
        log_config_change(session.get('user'), f'rôle supprimé: {role.name}')
        _flash('flash_role_deleted', 'success', name=role_name)
    except ValueError as exc:
        key = str(exc)
        _flash(key if key.startswith('flash_') else 'flash_role_system_protected', 'error')
    return redirect(_REDIRECT)


@bp.route('/admin/users/<username>/roles', methods=['POST'])
def set_user_roles_route(username):
    g = superadmin_guard()
    if g:
        return g
    if not is_valid_username(username):
        return jsonify({'error': 'invalid username'}), 400
    user = get_user(username)
    if user is None:
        _flash('flash_user_not_found', 'error')
        return redirect(_REDIRECT)
    if user.superadmin:
        _flash('flash_superadmin_perms_locked', 'error')
        return redirect(_REDIRECT)
    role_ids = []
    for role in get_all_roles():
        if request.form.get(f'role_{role.id}'):
            role_ids.append(role.id)
    set_user_roles(username, role_ids)
    log_config_change(session.get('user'), f'rôles {username}: {", ".join(str(r) for r in role_ids) or "aucun"}')
    _flash('flash_user_roles_updated', 'success', username=username)
    return redirect(_REDIRECT)
