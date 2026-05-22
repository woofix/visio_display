# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from datetime import date

from flask import render_template, request, session

from app_bootstrap import measure_perf_step
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
from services.config_svc import (
    get_default_screen_key,
    get_default_screen_name,
    get_screen_keys,
    load_config,
    normalize_screen_key,
)
from services.ephemeris_svc import get_school_zone
from services.i18n import _t
from services.media_svc import get_logo_path
from db import RolePermission, UserRole
from services.rbac_svc import get_all_roles
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


def _build_user_role_maps(users):
    roles = get_all_roles()
    role_by_id = {role.id: role for role in roles}
    role_permissions = {role.id: set() for role in roles}
    role_ids = list(role_by_id)
    if role_ids:
        for row in RolePermission.query.filter(RolePermission.role_id.in_(role_ids)).all():
            role_permissions.setdefault(row.role_id, set()).add(row.permission)

    user_roles = {username: [] for username in users.keys()}
    user_role_permissions = {username: set() for username in users.keys()}
    if users:
        rows = UserRole.query.filter(UserRole.username.in_(list(users.keys()))).all()
        for row in rows:
            role = role_by_id.get(row.role_id)
            if role is None:
                continue
            user_roles.setdefault(row.username, []).append(role.display_name)
            user_role_permissions.setdefault(row.username, set()).update(role_permissions.get(row.role_id, set()))

    return (
        roles,
        user_roles,
        {username: sorted(perms) for username, perms in user_role_permissions.items()},
    )


def _build_settings_context(tab='logo', install_defaults=None, install_result=None,
                            client_control_defaults=None, client_control_result=None):
    active_tab = normalize_settings_tab(tab)
    with measure_perf_step('settings.load_config'):
        cfg = load_config()
    client_watchdog = cfg.get('client_watchdog', {})
    with measure_perf_step('settings.is_superadmin'):
        is_sa = is_superadmin()
    if is_superadmin_settings_tab(active_tab) and not is_sa:
        active_tab = 'logo'

    needs_accounts = is_sa and active_tab in {'administration', 'accounts', 'add-account'}
    needs_screens = is_sa and active_tab in {'administration', 'accounts', 'screens'}
    needs_backups = is_sa and active_tab == 'sauvegardes'
    needs_installation = is_sa and active_tab == 'installation'
    needs_roles = is_sa and active_tab in {'administration', 'accounts', 'add-account'}

    backup_remote = cfg.get('backup_remote', {}) if is_sa else {}
    backup_remote_defaults = {
        'enabled': bool(backup_remote.get('enabled')),
        'url': str(backup_remote.get('url', '') or ''),
        'username': str(backup_remote.get('username', '') or ''),
        'password': '',
    }
    with measure_perf_step('settings.backup_schedule'):
        backup_schedule = get_backup_schedule(cfg) if needs_backups else {}
    backup_retention = {
        'max_versions': backup_retention_limit(cfg),
    } if needs_backups else {'max_versions': backup_retention_limit(cfg)}
    with measure_perf_step('settings.load_users'):
        users = load_users() if (needs_accounts or active_tab in {'theme', 'language', 'password'}) else {}
    if is_sa:
        for entry in users.values():
            if isinstance(entry, dict) and isinstance(entry.get('screens'), list):
                entry['screens'] = [normalize_screen_key(screen, cfg) for screen in entry['screens']]
    default_screen_key = get_default_screen_key(cfg)
    default_screen_label = get_default_screen_name(cfg) or _t('media_screen_default')
    all_screens = get_screen_keys(cfg) if needs_screens else []
    screen_labels = {
        screen_name: (default_screen_label if screen_name == default_screen_key else screen_name)
        for screen_name in all_screens
    }
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
    effective_permissions_map = {}
    role_permissions_map = {}
    all_roles = []
    user_roles_map = {}
    if needs_roles:
        with measure_perf_step('settings.role_maps'):
            all_roles, user_roles_map, role_permissions_map = _build_user_role_maps(users)
        for account_name, account_entry in users.items():
            direct_permissions = set(account_entry.get('permissions', [])) if isinstance(account_entry, dict) else set()
            role_permissions = set(role_permissions_map.get(account_name, []))
            role_permissions_map[account_name] = sorted(role_permissions)
            effective_permissions_map[account_name] = sorted(direct_permissions | role_permissions)
    with measure_perf_step('settings.known_clients'):
        known_clients = list_known_clients() if needs_installation else []
    with measure_perf_step('settings.list_backups'):
        available_backups = list_backups() if needs_backups else []
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
        known_clients=known_clients,
        available_backups=available_backups,
        all_permissions=[(k, _t(lbl_key)) for k, lbl_key in ALL_PERMISSIONS] if is_sa else [],
        all_screens=all_screens,
        screen_labels=screen_labels,
        default_screen_key=default_screen_key,
        all_roles=all_roles,
        user_roles_map=user_roles_map,
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
