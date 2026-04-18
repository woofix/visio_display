from flask import redirect, url_for, jsonify
from services.users_svc import is_admin, is_superadmin, has_permission
from services.i18n import _flash


def admin_guard():
    if not is_admin():
        _flash('flash_please_login', 'error')
        return redirect(url_for('auth.login'))
    return None


def superadmin_guard():
    if not is_admin():
        _flash('flash_please_login', 'error')
        return redirect(url_for('auth.login'))
    if not is_superadmin():
        _flash('flash_superadmin_only', 'error')
        return redirect(url_for('admin.admin_page'))
    return None


def perm_guard(perm):
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    if not has_permission(perm):
        return jsonify({"error": "permission denied"}), 403
    return None
