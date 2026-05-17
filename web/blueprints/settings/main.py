# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from datetime import date

from flask import render_template, request, session

from blueprints.guards import admin_guard
from constants import (
    ALL_FEATURES,
    ALL_PERMISSIONS,
    DEFAULT_METEO_TZ,
    DEFAULT_METEO_VILLE,
    LAT,
    LNG,
    SCHOOL_ZONES,
)
from services.backup_svc import backup_retention_limit, list_backups
from services.backup_scheduler_svc import get_backup_schedule
from services.clients_svc import list_known_clients
from services.config_svc import load_config
from services.ephemeris_svc import get_school_zone
from services.i18n import _t
from services.media_svc import get_logo_path
from services.rbac_svc import get_all_roles, get_effective_permissions_for_user, get_user_roles
from services.settings_sections import (
    is_superadmin_settings_tab,
    normalize_settings_tab,
    settings_section_template,
    settings_section_url,
)
from services.users_svc import has_screen_access, is_superadmin, load_users

from . import bp


def _settings_topbar_subtitle(active_tab, is_sa):
    subtitles = {
        'logo': _t('settings_sub'),
        'admins': _t('superadmin_topbar_sub') if is_sa else _t('admins_no_management'),
        'administration': _t('superadmin_topbar_sub'),
        'priority-alert': _t('superadmin_priority_alert_desc'),
        'accounts': _t('superadmin_topbar_sub'),
        'add-account': _t('superadmin_new_account_desc'),
        'screens': _t('superadmin_screens_manage'),
        'password': _t('admins_change_password'),
        'theme': _t('theme_subtitle'),
        'application': _t('app_subtitle'),
        'meteo': _t('settings_meteo_subtitle'),
        'language': _t('language_subtitle'),
        'installation': _t('install_subtitle'),
        'sauvegardes': _t('backup_subtitle'),
        'features': _t('features_info_banner'),
    }
    return subtitles.get(active_tab, _t('settings_topbar_sub'))


def _build_settings_context(tab='logo', install_defaults=None, install_result=None,
                            client_control_defaults=None, client_control_result=None):
    cfg = load_config()
    client_watchdog = cfg.get('client_watchdog', {})
    is_sa = is_superadmin()
    backup_remote = cfg.get('backup_remote', {}) if is_sa else {}
    backup_remote_defaults = {
        'enabled': bool(backup_remote.get('enabled')),
        'url': str(backup_remote.get('url', '') or ''),
        'username': str(backup_remote.get('username', '') or ''),
        'password': '',
    }
    backup_schedule = get_backup_schedule(cfg) if is_sa else {}
    backup_retention = {
        'max_versions': backup_retention_limit(cfg),
    } if is_sa else {}
    users = load_users()
    today = date.today()
    raw_events = cfg.get("events", [])
    events = []
    for ev in raw_events:
        try:
            ev_date = date.fromisoformat(ev["date"])
            delta = (ev_date - today).days
        except (ValueError, KeyError):
            delta = None
        events.append({**ev, "delta": delta})
    username = session.get('user')
    entry = users.get(username, {})
    user_theme = entry.get('theme', 'violet') if isinstance(entry, dict) else 'violet'
    meteo_location = {
        "ville": cfg.get("meteo_ville", DEFAULT_METEO_VILLE),
        "lat": cfg.get("meteo_lat", LAT),
        "lng": cfg.get("meteo_lng", LNG),
        "tz": cfg.get("meteo_tz", DEFAULT_METEO_TZ),
        "school_zone": cfg.get("school_zone", "auto"),
        "resolved_school_zone": get_school_zone(cfg),
        "school_zone_label": dict(SCHOOL_ZONES).get(cfg.get("school_zone", "auto"), "Auto"),
    }
    screen_names = list(cfg.get('screens', {}).keys())
    manageable_screens = screen_names if is_sa else [name for name in screen_names if has_screen_access(name)]
    active_tab = normalize_settings_tab(tab)
    if is_superadmin_settings_tab(active_tab) and not is_sa:
        active_tab = 'logo'
    effective_permissions_map = {}
    role_permissions_map = {}
    if is_sa:
        for account_name, account_entry in users.items():
            direct_permissions = set(account_entry.get('permissions', [])) if isinstance(account_entry, dict) else set()
            role_permissions = set(get_effective_permissions_for_user(account_name))
            role_permissions_map[account_name] = sorted(role_permissions)
            effective_permissions_map[account_name] = sorted(direct_permissions | role_permissions)
    return dict(
        cfg=cfg,
        users=users,
        current_user=username,
        logo_path=get_logo_path(),
        events=events,
        current_user_is_superadmin=is_sa,
        backup_remote=backup_remote_defaults,
        backup_schedule=backup_schedule,
        backup_retention=backup_retention,
        theme=user_theme,
        settings_topbar_subtitle=_settings_topbar_subtitle(active_tab, is_sa),
        can_ephemeris=is_sa,
        meteo_location=meteo_location,
        school_zones=SCHOOL_ZONES,
        install_defaults=install_defaults or {
            'host': '',
            'port': '22',
            'ssh_user': '',
            'kiosk_user': '',
            'server_url': '',
            'screen_name': '',
            'machine_name': '',
            'sudo_same_as_ssh': True,
        },
        install_result=install_result,
        client_control_defaults=client_control_defaults or {
            'host': '',
            'port': '22',
            'ssh_user': '',
            'sudo_same_as_ssh': True,
        },
        client_control_result=client_control_result,
        client_watchdog={
            'check_interval_seconds': int(client_watchdog.get('check_interval_seconds', 30) or 30),
            'grace_period_seconds': int(client_watchdog.get('grace_period_seconds', 90) or 90),
            'consecutive_failures_before_reboot': int(
                client_watchdog.get('consecutive_failures_before_reboot', 1) or 1
            ),
        },
        known_clients=list_known_clients() if is_sa else [],
        available_backups=list_backups() if is_sa else [],
        all_permissions=[(k, _t(lbl_key)) for k, lbl_key in ALL_PERMISSIONS] if is_sa else [],
        all_screens=['', *cfg.get('screens', {}).keys()] if is_sa else [],
        all_roles=get_all_roles() if is_sa else [],
        user_roles_map={u: [r.display_name for r in get_user_roles(u)] for u in users.keys()} if is_sa else {},
        user_effective_permissions_map=effective_permissions_map,
        user_role_permissions_map=role_permissions_map,
        manageable_screens=manageable_screens,
        priority_alert=cfg.get('priority_alert', {}) if is_sa else {},
        tab=active_tab,
        settings_section_url=settings_section_url,
        all_features=ALL_FEATURES if is_sa else [],
        features=cfg.get('features', {}) if is_sa else {},
    )


def _normalize_positive_int(raw_value, default_value, minimum, maximum):
    try:
        value = int(str(raw_value or '').strip())
    except (TypeError, ValueError):
        return default_value
    return max(minimum, min(maximum, value))


@bp.route('/admin/settings')
def admin_settings_page():
    redir = admin_guard()
    if redir: return redir
    context = _build_settings_context(tab=request.args.get('tab', 'logo'))
    return render_template(settings_section_template(context['tab']), **context)


@bp.route('/admin/settings/<section>')
def admin_settings_section_page(section):
    redir = admin_guard()
    if redir: return redir
    context = _build_settings_context(tab=section)
    return render_template(settings_section_template(context['tab']), **context)
