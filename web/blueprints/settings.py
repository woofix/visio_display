import os
from datetime import date

from flask import Blueprint, request, redirect, url_for, session, render_template

from constants import (
    VALID_THEMES, LOGO_EXTS, IMAGES_FOLDER, DEFAULT_LOGO, LAT, LNG,
    DEFAULT_METEO_VILLE, DEFAULT_METEO_TZ, SCHOOL_ZONES, ALL_FEATURES,
)
from services.config_svc import load_config, save_config
from services.users_svc import load_users, save_users, is_superadmin, has_permission
from services.media_svc import get_logo_path
from services.i18n import _flash
from blueprints.guards import admin_guard, superadmin_guard
from services.ephemeris_svc import get_school_zone

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
    meteo_location = {
        "ville": cfg.get("meteo_ville", DEFAULT_METEO_VILLE),
        "lat":   cfg.get("meteo_lat",   LAT),
        "lng":   cfg.get("meteo_lng",   LNG),
        "tz":    cfg.get("meteo_tz",    DEFAULT_METEO_TZ),
        "school_zone": cfg.get("school_zone", "auto"),
        "resolved_school_zone": get_school_zone(cfg),
        "school_zone_label": dict(SCHOOL_ZONES).get(cfg.get("school_zone", "auto"), "Auto"),
    }
    return render_template('admin_settings.html',
        cfg=cfg, users=users, current_user=username,
        logo_path=get_logo_path(),
        events=events,
        current_user_is_superadmin=is_superadmin(),
        theme=user_theme,
        can_ephemeris=has_permission('ephemeris'),
        meteo_location=meteo_location,
        school_zones=SCHOOL_ZONES,
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
        return redirect(url_for('settings.admin_settings_page') + '?tab=meteo')
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        if not (-90 <= lat_f <= 90) or not (-180 <= lng_f <= 180):
            raise ValueError("out of range")
    except (ValueError, TypeError):
        _flash('flash_meteo_invalid', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=meteo')
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
    # Régénérer l'éphéméride avec la nouvelle localisation
    from services.ephemeris_svc import generate_ephemeride_image
    generate_ephemeride_image(force=True)
    _flash('flash_meteo_updated', 'success', ville=ville)
    return redirect(url_for('settings.admin_settings_page') + '?tab=meteo')


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


@bp.route('/admin/features')
def admin_features_page():
    g = superadmin_guard()
    if g: return g
    cfg = load_config()
    return render_template('admin_features.html',
        all_features=ALL_FEATURES,
        features=cfg.get('features', {}),
        current_user=session.get('user'),
        logo_path=get_logo_path())


@bp.route('/admin/features/toggle', methods=['POST'])
def toggle_feature():
    g = superadmin_guard()
    if g: return g
    feature = request.form.get('feature', '').strip()
    valid_keys = {k for k, _, _ in ALL_FEATURES}
    if feature not in valid_keys:
        _flash('flash_feature_disabled_access', 'error')
        return redirect(url_for('settings.admin_features_page'))
    cfg = load_config()
    features = dict(cfg.get('features', {}))
    features[feature] = not bool(features.get(feature, True))
    cfg['features'] = features
    save_config(cfg)
    _flash('flash_feature_updated', 'success')
    return redirect(url_for('settings.admin_features_page'))


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
