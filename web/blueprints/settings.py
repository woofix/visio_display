import os
from datetime import date

from flask import Blueprint, request, redirect, url_for, session, render_template

from constants import VALID_THEMES, LOGO_EXTS, IMAGES_FOLDER, DEFAULT_LOGO
from services.config_svc import load_config, save_config
from services.users_svc import load_users, save_users, is_superadmin, has_permission
from services.media_svc import get_logo_path
from services.i18n import _flash
from blueprints.guards import admin_guard, superadmin_guard

bp = Blueprint('settings', __name__)


@bp.route('/admin/settings')
def admin_settings_page():
    redir = admin_guard()
    if redir: return redir
    cfg        = load_config()
    users      = load_users()
    today      = date.today()
    raw_events = cfg.get("events", [])
    events     = []
    for ev in raw_events:
        try:
            ev_date = date.fromisoformat(ev["date"])
            delta   = (ev_date - today).days
        except (ValueError, KeyError):
            delta = None
        events.append({**ev, "delta": delta})
    username   = session.get('user')
    entry      = users.get(username, {})
    user_theme = entry.get('theme', 'violet') if isinstance(entry, dict) else 'violet'
    return render_template('admin_settings.html',
        cfg=cfg, users=users, current_user=username,
        logo_path=get_logo_path(),
        events=events,
        current_user_is_superadmin=is_superadmin(),
        theme=user_theme,
        can_ephemeris=has_permission('ephemeris'),
        tab=request.args.get('tab', 'logo'))


@bp.route('/admin/settings/appname', methods=['POST'])
def set_appname():
    redir = superadmin_guard()
    if redir: return redir
    name = request.form.get('app_name', '').strip()
    if name:
        cfg = load_config()
        cfg['app_name'] = name
        save_config(cfg)
        _flash('flash_appname_updated', 'success')
    return redirect(url_for('settings.admin_settings_page') + '?tab=application')


@bp.route('/admin/settings/theme', methods=['POST'])
def set_theme():
    redir = admin_guard()
    if redir: return redir
    theme = request.form.get('theme', 'violet')
    if theme not in VALID_THEMES:
        theme = 'violet'
    users    = load_users()
    username = session.get('user')
    if username in users:
        users[username]['theme'] = theme
        save_users(users)
    _flash('flash_theme_updated', 'success')
    return redirect(url_for('settings.admin_settings_page') + '?tab=theme')


@bp.route('/admin/settings/language', methods=['POST'])
def set_language():
    redir = admin_guard()
    if redir: return redir
    lang = request.form.get('language', 'fr')
    if lang not in ('fr', 'en'):
        lang = 'fr'
    users    = load_users()
    username = session.get('user')
    if username in users:
        users[username]['language'] = lang
        save_users(users)
    _flash('flash_language_updated', 'success')
    return redirect(url_for('settings.admin_settings_page') + '?tab=language')


@bp.route('/admin/logo/upload', methods=['POST'])
def upload_logo():
    redir = admin_guard()
    if redir: return redir
    if not has_permission('logo'):
        _flash('flash_no_perm_logo', 'error')
        return redirect(url_for('settings.admin_settings_page'))
    file = request.files.get('logo')
    if not file or file.filename == '':
        _flash('flash_no_file', 'error')
        return redirect(url_for('admin.admin_page'))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in LOGO_EXTS:
        _flash('flash_logo_format', 'error')
        return redirect(url_for('admin.admin_page'))
    filename = f'logo_custom{ext}'
    file.save(os.path.join(IMAGES_FOLDER, filename))
    cfg = load_config()
    cfg['logo'] = filename
    save_config(cfg)
    _flash('flash_logo_updated', 'success')
    return redirect(url_for('admin.admin_page'))


@bp.route('/admin/logo/reset', methods=['POST'])
def reset_logo():
    redir = admin_guard()
    if redir: return redir
    if not has_permission('logo'):
        _flash('flash_no_perm_logo', 'error')
        return redirect(url_for('settings.admin_settings_page'))
    cfg = load_config()
    cfg['logo'] = DEFAULT_LOGO
    save_config(cfg)
    _flash('flash_logo_reset', 'success')
    return redirect(url_for('admin.admin_page'))
