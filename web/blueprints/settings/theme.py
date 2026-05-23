# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os

from flask import redirect, request, session

from blueprints.guards import admin_guard, superadmin_guard
from constants import DEFAULT_LOGO, DEFAULT_METEO_TZ, IMAGES_FOLDER, LOGO_EXTS, SCHOOL_ZONES, VALID_THEMES
from services.activity_svc import log_config_change
from services.config_svc import load_config, save_config
from services.i18n import _flash
from services.media_svc import is_safe_svg_file, is_valid_uploaded_image
from services.settings_sections import settings_section_url
from services.users_svc import has_permission, update_user_theme

from . import bp


@bp.route('/admin/settings/appname', methods=['POST'])
def set_appname():
    redir = superadmin_guard()
    if redir: return redir
    name = request.form.get('app_name', '').strip()
    if name:
        cfg = load_config()
        cfg['app_name'] = name
        save_config(cfg)
        log_config_change(session.get('user'), f'nom application:{name}')
        _flash('flash_appname_updated', 'success')
    return redirect(settings_section_url('application'))


@bp.route('/admin/settings/meteo', methods=['POST'])
def set_meteo_location():
    redir = superadmin_guard()
    if redir: return redir
    ville = request.form.get('meteo_ville', '').strip()
    lat   = request.form.get('meteo_lat',   '').strip()
    lng   = request.form.get('meteo_lng',   '').strip()
    tz    = request.form.get('meteo_tz',    '').strip()
    school_zone = request.form.get('school_zone', 'auto').strip() or 'auto'
    if not ville:
        _flash('flash_meteo_invalid', 'error')
        return redirect(settings_section_url('meteo'))
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        if not (-90 <= lat_f <= 90) or not (-180 <= lng_f <= 180):
            raise ValueError("out of range")
    except (ValueError, TypeError):
        _flash('flash_meteo_invalid', 'error')
        return redirect(settings_section_url('meteo'))
    if not tz:
        tz = DEFAULT_METEO_TZ
    valid_school_zones = {value for value, _label in SCHOOL_ZONES}
    if school_zone not in valid_school_zones:
        school_zone = 'auto'
    cfg = load_config()
    cfg['meteo_ville'] = ville
    cfg['meteo_lat']   = lat_f
    cfg['meteo_lng']   = lng_f
    cfg['meteo_tz']    = tz
    cfg['school_zone'] = school_zone
    save_config(cfg)
    log_config_change(session.get('user'), f'weather:{ville} ({lat_f},{lng_f}) tz={tz} zone={school_zone}')
    from services.ephemeris_svc import ensure_ephemeride_image_async
    ensure_ephemeride_image_async(force=True)
    _flash('flash_meteo_updated', 'success', ville=ville)
    return redirect(settings_section_url('meteo'))


@bp.route('/admin/settings/theme', methods=['POST'])
def set_theme():
    redir = admin_guard()
    if redir: return redir
    theme = request.form.get('theme', 'violet')
    if theme not in VALID_THEMES:
        theme = 'violet'
    username = session.get('user')
    if username:
        update_user_theme(username, theme)
        log_config_change(username, f'theme:{theme}')
    _flash('flash_theme_updated', 'success')
    return redirect(settings_section_url('theme'))


@bp.route('/admin/logo/upload', methods=['POST'])
def upload_logo():
    redir = admin_guard()
    if redir: return redir
    if not has_permission('logo'):
        _flash('flash_no_perm_logo', 'error')
        return redirect(settings_section_url('logo'))
    file = request.files.get('logo')
    if not file or file.filename == '':
        _flash('flash_no_file', 'error')
        return redirect(settings_section_url('logo'))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in LOGO_EXTS:
        _flash('flash_logo_format', 'error')
        return redirect(settings_section_url('logo'))
    filename = f'logo_custom{ext}'
    path = os.path.join(IMAGES_FOLDER, filename)
    file.save(path)
    if ext == '.svg':
        if not is_safe_svg_file(path):
            os.remove(path)
            _flash('flash_logo_unsafe', 'error')
            return redirect(settings_section_url('logo'))
    elif not is_valid_uploaded_image(path):
        os.remove(path)
        _flash('flash_logo_invalid', 'error')
        return redirect(settings_section_url('logo'))
    cfg = load_config()
    cfg['logo'] = filename
    save_config(cfg)
    log_config_change(session.get('user'), f'logo updated:{filename}')
    _flash('flash_logo_updated', 'success')
    return redirect(settings_section_url('logo'))


@bp.route('/admin/logo/reset', methods=['POST'])
def reset_logo():
    redir = admin_guard()
    if redir: return redir
    if not has_permission('logo'):
        _flash('flash_no_perm_logo', 'error')
        return redirect(settings_section_url('logo'))
    cfg = load_config()
    cfg['logo'] = DEFAULT_LOGO
    save_config(cfg)
    log_config_change(session.get('user'), 'logo reset')
    _flash('flash_logo_reset', 'success')
    return redirect(settings_section_url('logo'))
