# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import queue
import threading
from datetime import date

from flask import Blueprint, request, redirect, url_for, session, render_template, jsonify, send_file, Response, stream_with_context, current_app, flash

from constants import (
    VALID_THEMES, LOGO_EXTS, IMAGES_FOLDER, DEFAULT_LOGO, LAT, LNG,
    DEFAULT_METEO_VILLE, DEFAULT_METEO_TZ, SCHOOL_ZONES, ALL_FEATURES,
    ALL_PERMISSIONS,
)
from services.activity_svc import log_config_change
from services.backup_svc import (
    backup_path,
    copy_backup_to_smb,
    create_backup_archive,
    delete_backup_archive,
    list_backups,
    restore_backup_archive,
)
from services.clients_svc import list_known_clients
from services.config_svc import load_config, save_config
from services.rbac_svc import get_all_roles, get_effective_permissions_for_user, get_user_roles
from services.users_svc import (
    has_permission,
    has_screen_access,
    is_superadmin,
    load_users,
    update_user_language,
    update_user_theme,
)
from services.media_svc import get_logo_path
from services.media_svc import is_safe_svg_file, is_valid_uploaded_image
from services.i18n import _flash, _t
from blueprints.guards import admin_guard, superadmin_guard
from services.ephemeris_svc import get_school_zone
from services.deploy_svc import (
    deploy_client_install,
    deploy_client_os_update,
    deploy_client_power_action,
    deploy_client_update,
)

bp = Blueprint('settings', __name__)


def _normalize_machine_name(raw_value):
    value = (raw_value or '').strip().lower()
    allowed = 'abcdefghijklmnopqrstuvwxyz0123456789-'
    normalized = []
    previous_dash = False
    for char in value:
        if char in allowed:
            if char == '-':
                if previous_dash:
                    continue
                previous_dash = True
            else:
                previous_dash = False
            normalized.append(char)
        elif not previous_dash and normalized:
            normalized.append('-')
            previous_dash = True
    result = ''.join(normalized).strip('-')
    return result[:63]


def _normalize_settings_tab(raw_tab):
    tab = (raw_tab or 'logo').strip().lower()
    aliases = {
        'events': 'meteo',
        'event': 'meteo',
        'evenements': 'meteo',
        'install': 'installation',
        'installer': 'installation',
        'superadmin': 'administration',
        'alerte-prioritaire': 'priority-alert',
        'alert': 'priority-alert',
        'comptes-permissions': 'accounts',
        'users': 'accounts',
        'utilisateurs': 'accounts',
        'ajouter-compte': 'add-account',
        'gestion-ecrans': 'screens',
        'mot-de-passe': 'password',
        'backup': 'sauvegardes',
        'backups': 'sauvegardes',
        'fonctionnalites': 'features',
        'features': 'features',
    }
    return aliases.get(tab, tab)


def settings_section_url(tab):
    tab = _normalize_settings_tab(tab)
    slugs = {
        'logo': 'logo',
        'admins': 'admins',
        'password': 'mot-de-passe',
        'administration': 'administration',
        'priority-alert': 'alerte-prioritaire',
        'accounts': 'comptes-permissions',
        'add-account': 'ajouter-compte',
        'screens': 'gestion-ecrans',
        'theme': 'theme',
        'application': 'application',
        'meteo': 'meteo',
        'language': 'language',
        'installation': 'installation',
        'sauvegardes': 'sauvegardes',
        'features': 'fonctionnalites',
    }
    return f"/admin/settings/{slugs.get(tab, 'logo')}"


def settings_section_template(tab):
    tab = _normalize_settings_tab(tab)
    templates = {
        'logo': 'admin_settings_logo.html',
        'admins': 'admin_settings_admins.html',
        'password': 'admin_settings_password.html',
        'administration': 'admin_settings_accounts.html',
        'priority-alert': 'admin_settings_priority_alert.html',
        'accounts': 'admin_settings_accounts.html',
        'add-account': 'admin_settings_add_account.html',
        'screens': 'admin_settings_screens.html',
        'theme': 'admin_settings_theme.html',
        'application': 'admin_settings_application.html',
        'meteo': 'admin_settings_meteo.html',
        'language': 'admin_settings_language.html',
        'installation': 'admin_settings_installation.html',
        'sauvegardes': 'admin_settings_backups.html',
        'features': 'admin_settings_features.html',
    }
    return templates.get(tab, 'admin_settings_logo.html')


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
    active_tab = _normalize_settings_tab(tab)
    if active_tab in {'installation', 'sauvegardes', 'administration', 'priority-alert', 'accounts', 'add-account', 'screens', 'features', 'meteo'} and not is_sa:
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


def _build_backup_remote_settings_from_form(current_settings=None):
    current_settings = current_settings or {}
    password = str(request.form.get('password', '') or '').strip()
    return {
        'enabled': request.form.get('enabled') == 'on',
        'url': str(request.form.get('url', '') or '').strip(),
        'username': str(request.form.get('username', '') or '').strip(),
        'password': password if password else str(current_settings.get('password', '') or '').strip(),
    }


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


@bp.route('/admin/settings/client-watchdog', methods=['POST'])
def set_client_watchdog():
    redir = superadmin_guard()
    if redir:
        return redir

    cfg = load_config()
    current = cfg.get('client_watchdog', {})
    cfg['client_watchdog'] = {
        'check_interval_seconds': _normalize_positive_int(
            request.form.get('check_interval_seconds'),
            int(current.get('check_interval_seconds', 30) or 30),
            15,
            600,
        ),
        'grace_period_seconds': _normalize_positive_int(
            request.form.get('grace_period_seconds'),
            int(current.get('grace_period_seconds', 90) or 90),
            30,
            3600,
        ),
        'consecutive_failures_before_reboot': _normalize_positive_int(
            request.form.get('consecutive_failures_before_reboot'),
            int(current.get('consecutive_failures_before_reboot', 1) or 1),
            1,
            20,
        ),
    }
    save_config(cfg)
    log_config_change(session.get('user'), f'client watchdog updated: interval={cfg["client_watchdog"]["check_interval_seconds"]}s, grace={cfg["client_watchdog"]["grace_period_seconds"]}s, failures={cfg["client_watchdog"]["consecutive_failures_before_reboot"]}')
    _flash('flash_client_watchdog_updated', 'success')
    return redirect(settings_section_url('installation'))


@bp.route('/admin/settings/known-clients')
def known_clients_json():
    redir = superadmin_guard()
    if redir:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403
    return jsonify({
        'ok': True,
        'clients': list_known_clients(),
    })


@bp.route('/admin/settings/backups/create', methods=['POST'])
def create_backup():
    redir = superadmin_guard()
    if redir:
        return redir

    backup = create_backup_archive()
    log_config_change(session.get('user'), f"backup created: {backup['filename']}")
    _flash('flash_backup_created', 'success', filename=backup['filename'])
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/remote', methods=['POST'])
def save_backup_remote():
    redir = superadmin_guard()
    if redir:
        return redir

    cfg = load_config()
    remote_settings = _build_backup_remote_settings_from_form(cfg.get('backup_remote', {}))
    if remote_settings['enabled'] and not remote_settings['url']:
        _flash('flash_backup_remote_missing_url', 'error')
        return redirect(settings_section_url('sauvegardes'))
    if remote_settings['url'] and not remote_settings['url'].lower().startswith('smb://'):
        _flash('flash_backup_remote_invalid_url', 'error')
        return redirect(settings_section_url('sauvegardes'))

    cfg['backup_remote'] = remote_settings
    save_config(cfg)
    log_config_change(
        session.get('user'),
        f"backup SMB destination updated: active={'yes' if remote_settings['enabled'] else 'no'}, url={remote_settings['url'] or '-'}",
    )
    _flash('flash_backup_remote_saved', 'success')
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/create-stream', methods=['POST'])
def create_backup_stream():
    redir = superadmin_guard()
    if redir:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    app = current_app._get_current_object()
    username = session.get('user')
    events = queue.Queue()
    done = threading.Event()

    def emit(event_type, **payload):
        events.put({'type': event_type, **payload})

    def serialize_backup(backup):
        return {
            'filename': backup.get('filename'),
            'size': backup.get('size'),
            'size_bytes': backup.get('size_bytes'),
            'created_at_iso': backup.get('created_at_iso'),
        }

    def worker():
        try:
            with app.app_context():
                backup = create_backup_archive(progress_callback=lambda message: emit('log', message=message))
                log_config_change(username, f"backup created: {backup['filename']}")
            emit('done', backup=serialize_backup(backup))
        except Exception as exc:
            emit('error', message=str(exc) or exc.__class__.__name__)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield json.dumps({'type': 'log', 'message': 'Connecting to backup engine...'}) + '\n'
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload) + '\n'

    return Response(generate(), mimetype='application/x-ndjson')


@bp.route('/admin/settings/backups/download/<filename>')
def download_backup(filename):
    redir = superadmin_guard()
    if redir:
        return redir
    path = backup_path(filename)
    return send_file(path, as_attachment=True, download_name=filename)


@bp.route('/admin/settings/backups/copy/<filename>', methods=['POST'])
def copy_backup(filename):
    redir = superadmin_guard()
    if redir:
        return redir

    cfg = load_config()
    remote_settings = cfg.get('backup_remote', {})
    if not remote_settings.get('enabled') or not remote_settings.get('url'):
        _flash('flash_backup_remote_not_configured', 'error')
        return redirect(settings_section_url('sauvegardes'))

    try:
        path = backup_path(filename)
        copy_backup_to_smb(path, filename, remote_settings)
    except FileNotFoundError:
        _flash('flash_backup_delete_missing', 'error')
    except Exception as exc:
        flash(str(exc) or _t('backup_stream_error'), 'error')
    else:
        log_config_change(session.get('user'), f"backup copied to SMB: {filename}")
        _flash('flash_backup_copied', 'success', filename=filename)
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/delete/<filename>', methods=['POST'])
def delete_backup(filename):
    redir = superadmin_guard()
    if redir:
        return redir

    try:
        delete_backup_archive(filename)
    except FileNotFoundError:
        _flash('flash_backup_delete_missing', 'error')
    else:
        log_config_change(session.get('user'), f"backup deleted: {filename}")
        _flash('flash_backup_deleted', 'success', filename=filename)
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/restore', methods=['POST'])
def restore_backup():
    redir = superadmin_guard()
    if redir:
        return redir

    uploaded = request.files.get('backup_file')
    if uploaded is None or not uploaded.filename:
        _flash('flash_backup_file_missing', 'error')
        return redirect(settings_section_url('sauvegardes'))

    try:
        restore_backup_archive(uploaded)
    except Exception as exc:
        flash(str(exc) or _t('flash_backup_restore_failed'), 'error')
        return redirect(settings_section_url('sauvegardes'))

    log_config_change(session.get('user'), f"backup restored: {uploaded.filename}")
    _flash('flash_backup_restored', 'success', filename=uploaded.filename)
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/install-client', methods=['POST'])
def install_client():
    redir = superadmin_guard()
    if redir: return redir

    host = request.form.get('host', '').strip()
    ssh_user = request.form.get('ssh_user', '').strip()
    kiosk_user = request.form.get('kiosk_user', '').strip()
    server_url = request.form.get('server_url', '').strip().rstrip('/')
    screen_name = request.form.get('screen_name', '').strip()
    machine_name = _normalize_machine_name(request.form.get('machine_name', ''))
    ssh_password = request.form.get('ssh_password', '')
    sudo_same_as_ssh = request.form.get('sudo_same_as_ssh') == 'on'
    sudo_password = '' if sudo_same_as_ssh else request.form.get('sudo_password', '')
    port_raw = request.form.get('port', '22').strip() or '22'

    try:
        port = int(port_raw)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _flash('flash_install_invalid_port', 'error')
        return redirect(settings_section_url('installation'))

    if not host or not ssh_user or not kiosk_user or not server_url or not machine_name or not ssh_password:
        _flash('flash_install_missing_fields', 'error')
        return redirect(settings_section_url('installation'))
    if not sudo_same_as_ssh and not sudo_password:
        _flash('flash_install_missing_sudo_password', 'error')
        return redirect(settings_section_url('installation'))

    install_result = deploy_client_install(
        host=host,
        port=port,
        ssh_user=ssh_user,
        kiosk_user=kiosk_user,
        server_url=server_url,
        screen_name=screen_name,
        machine_name=machine_name,
        ssh_password=ssh_password,
        sudo_password=sudo_password,
    )
    install_result['summary'] = _t(install_result.get('summary_key', ''))

    if install_result.get('ok'):
        log_config_change(session.get('user'), f'client install started:{host} ({machine_name})')
        _flash('flash_install_success', 'success', host=host)
    else:
        _flash('flash_install_failed', 'error', host=host)

    return render_template(
        settings_section_template('installation'),
        **_build_settings_context(
            tab='installation',
            install_defaults={
                'host': host,
                'port': str(port),
                'ssh_user': ssh_user,
                'kiosk_user': kiosk_user,
                'server_url': server_url,
                'screen_name': screen_name,
                'machine_name': machine_name,
                'sudo_same_as_ssh': sudo_same_as_ssh,
            },
            install_result=install_result,
        )
    )


@bp.route('/admin/settings/client-power', methods=['POST'])
def control_client_power():
    redir = superadmin_guard()
    if redir: return redir

    host = request.form.get('host', '').strip()
    ssh_user = request.form.get('ssh_user', '').strip()
    ssh_password = request.form.get('ssh_password', '')
    sudo_same_as_ssh = request.form.get('sudo_same_as_ssh') == 'on'
    sudo_password = '' if sudo_same_as_ssh else request.form.get('sudo_password', '')
    action = request.form.get('action', '').strip().lower()
    if action == 'reboot':
        action = 'restart'
    port_raw = request.form.get('port', '22').strip() or '22'

    try:
        port = int(port_raw)
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        _flash('flash_install_invalid_port', 'error')
        return redirect(settings_section_url('installation'))

    if action not in {'shutdown', 'restart', 'update', 'os-update'}:
        _flash('flash_client_control_invalid_action', 'error')
        return redirect(settings_section_url('installation'))
    if not host or not ssh_user or not ssh_password:
        _flash('flash_client_control_missing_fields', 'error')
        return redirect(settings_section_url('installation'))
    if not sudo_same_as_ssh and not sudo_password:
        _flash('flash_install_missing_sudo_password', 'error')
        return redirect(settings_section_url('installation'))

    if action == 'update':
        client_control_result = deploy_client_update(
            host=host,
            port=port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            sudo_password=sudo_password,
        )
    elif action == 'os-update':
        client_control_result = deploy_client_os_update(
            host=host,
            port=port,
            ssh_user=ssh_user,
            ssh_password=ssh_password,
            sudo_password=sudo_password,
        )
    else:
        client_control_result = deploy_client_power_action(
            host=host,
            port=port,
            ssh_user=ssh_user,
            action=action,
            ssh_password=ssh_password,
            sudo_password=sudo_password,
        )
    client_control_result['summary'] = _t(client_control_result.get('summary_key', ''))

    action_key = action.replace('-', '_')
    if client_control_result.get('ok'):
        log_config_change(session.get('user'), f'action client:{action}:{host}')
        _flash(
            'flash_client_control_success',
            'success',
            action=_t(f'client_control_action_{action_key}'),
            host=host,
        )
    else:
        _flash(
            'flash_client_control_failed',
            'error',
            action=_t(f'client_control_action_{action_key}'),
            host=host,
        )

    return render_template(
        settings_section_template('installation'),
        **_build_settings_context(
            tab='installation',
            client_control_defaults={
                'host': host,
                'port': str(port),
                'ssh_user': ssh_user,
                'sudo_same_as_ssh': sudo_same_as_ssh,
            },
            client_control_result=client_control_result,
            install_defaults={
                'host': '',
                'port': '22',
                'ssh_user': '',
                'kiosk_user': '',
                'server_url': '',
                'screen_name': '',
                'machine_name': '',
                'sudo_same_as_ssh': True,
            },
        )
    )


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
    # Regenerate the ephemeris with the new location
    from services.ephemeris_svc import generate_ephemeride_image
    generate_ephemeride_image(force=True)
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


@bp.route('/admin/settings/language', methods=['POST'])
def set_language():
    redir = admin_guard()
    if redir: return redir
    lang = request.form.get('language', 'fr')
    if lang not in ('fr', 'en'):
        lang = 'fr'
    username = session.get('user')
    if username:
        update_user_language(username, lang)
        log_config_change(username, f'langue:{lang}')
    _flash('flash_language_updated', 'success')
    return redirect(settings_section_url('language'))


@bp.route('/admin/features')
def admin_features_page():
    g = superadmin_guard()
    if g: return g
    return redirect(settings_section_url('features'))


@bp.route('/admin/features/toggle', methods=['POST'])
def toggle_feature():
    g = superadmin_guard()
    if g: return g
    feature = request.form.get('feature', '').strip()
    valid_keys = {k for k, _, _ in ALL_FEATURES}
    if feature not in valid_keys:
        _flash('flash_feature_disabled_access', 'error')
        _flash('flash_feature_disabled_access', 'error')
        return redirect(settings_section_url('features'))
    cfg = load_config()
    features = dict(cfg.get('features', {}))
    features[feature] = not bool(features.get(feature, True))
    cfg['features'] = features
    save_config(cfg)
    log_config_change(session.get('user'), f'feature {feature}: {features[feature]}')
    _flash('flash_feature_updated', 'success')
    return redirect(settings_section_url('features'))


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
