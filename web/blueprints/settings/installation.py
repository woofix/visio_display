# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os

from flask import current_app, jsonify, redirect, render_template, request, session

from blueprints.guards import superadmin_guard
from services.activity_svc import log_config_change
from services.clients_svc import list_known_clients
from services.config_svc import load_config, save_config
from services.deploy_svc import (
    deploy_client_install,
    deploy_client_os_update,
    deploy_client_power_action,
    deploy_client_update,
)
from services.i18n import _flash, _t
from services.settings_sections import settings_section_template, settings_section_url

from . import bp
from .main import _build_settings_context, _normalize_positive_int


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
    log_config_change(
        session.get('user'),
        f'client watchdog updated: interval={cfg["client_watchdog"]["check_interval_seconds"]}s, '
        f'grace={cfg["client_watchdog"]["grace_period_seconds"]}s, '
        f'failures={cfg["client_watchdog"]["consecutive_failures_before_reboot"]}',
    )
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


@bp.route('/admin/settings/install-client', methods=['POST'])
def install_client():
    redir = superadmin_guard()
    if redir: return redir

    host = request.form.get('host', '').strip()
    ssh_user = request.form.get('ssh_user', '').strip()
    kiosk_user = request.form.get('kiosk_user', '').strip()
    server_url = request.form.get('server_url', '').strip()
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
        heartbeat_token=os.environ.get('CLIENT_HEARTBEAT_TOKEN', '').strip(),
        screen_token=current_app.config.get('DISPLAY_API_TOKEN', ''),
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
