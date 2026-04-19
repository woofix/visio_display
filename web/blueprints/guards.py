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


def feature_guard(feature_name):
    from services.config_svc import is_feature_enabled
    if not is_feature_enabled(feature_name):
        _flash('flash_feature_disabled_access', 'error')
        return redirect(url_for('admin.admin_page'))
    return None


def feature_guard_json(feature_name):
    from services.config_svc import is_feature_enabled
    if not is_feature_enabled(feature_name):
        return jsonify({"error": "feature disabled"}), 403
    return None
