# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import secrets
from flask import Blueprint, request, jsonify

from services.config_svc import (
    get_screen_halo_color,
    halo_color_to_rgb,
    is_feature_enabled,
    load_config,
)
from services.clients_svc import record_client_heartbeat
from services.display_token_svc import screen_token_is_valid
from services.users_svc import is_admin
from services.media_svc import (
    get_all_media, get_media_type, is_media_scheduled, get_disk_usage,
    is_media_disabled, get_media_groups, is_group_active_on_screen,
    get_media_url, get_original_media_url,
)
from services.campaign_svc import resolve_campaign_override
from services.ephemeris_svc import ensure_ephemeride_image_async
from constants import UPLOAD_FOLDER

bp = Blueprint('api', __name__)


def _screen_api_token_is_valid():
    return screen_token_is_valid(request)


def _screen_api_guard():
    if _screen_api_token_is_valid():
        return None
    return jsonify({"error": "screen_token_required"}), 403


def _requested_display_bounds():
    try:
        width = int(request.args.get('w', '') or 0)
        height = int(request.args.get('h', '') or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _media_path(filename, media_type, bounds):
    if filename.startswith('ephemeride_'):
        return get_original_media_url(filename)
    return get_media_url(
        filename,
        context='display',
        bounds=bounds,
        allow_original=True,
        generate_missing=False,
    ) or get_original_media_url(filename)


def _heartbeat_token_is_valid(data):
    expected = os.environ.get('CLIENT_HEARTBEAT_TOKEN', '').strip()
    if not expected:
        return False
    provided = (
        request.headers.get('X-Client-Token')
        or str(data.get('token') or '').strip()
    )
    return bool(provided) and secrets.compare_digest(provided, expected)


@bp.route('/api/config')
def api_config():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(load_config())


@bp.route('/api/priority-alert')
def api_priority_alert():
    guard = _screen_api_guard()
    if guard:
        return guard
    alert = load_config().get('priority_alert', {})
    return jsonify({
        'message': str(alert.get('message', '') or ''),
        'updated_at': alert.get('updated_at'),
    })


@bp.route('/api/client-policy')
def api_client_policy():
    watchdog = load_config().get('client_watchdog', {})
    return jsonify({
        'watchdog': {
            'check_interval_seconds': int(watchdog.get('check_interval_seconds', 30) or 30),
            'grace_period_seconds': int(watchdog.get('grace_period_seconds', 90) or 90),
            'consecutive_failures_before_reboot': int(
                watchdog.get('consecutive_failures_before_reboot', 1) or 1
            ),
        }
    })


@bp.route('/api/images')
def get_images():
    guard = _screen_api_guard()
    if guard:
        return guard
    if is_feature_enabled('ephemeris'):
        try:
            ensure_ephemeride_image_async()
        except Exception as exc:
            print(f"[EPHEMERIS REFRESH ERROR] {exc}")
    screen = request.args.get('screen', '').strip().lower()
    bounds = _requested_display_bounds()
    cfg    = load_config()
    campaign_override = resolve_campaign_override(cfg, screen=screen)

    if screen and screen in cfg.get('screens', {}):
        scfg      = cfg['screens'][screen]
        effective_cfg = dict(scfg)
        effective_cfg['groups'] = cfg.get('groups', {})
        effective_cfg['group_screens'] = cfg.get('group_screens', {})
        if campaign_override:
            files = campaign_override.get('files', [])
        else:
            all_files = get_all_media(cfg)
            all_files_set = set(all_files)
            screen_order = scfg.get('order', [])
            if screen_order:
                assigned = [f for f in screen_order if f in all_files_set]
                ephemeride_extras = [f for f in all_files if f.startswith('ephemeride_') and f not in screen_order]
                files = assigned + ephemeride_extras
            else:
                files = all_files
        return jsonify([
            {"path": _media_path(f, get_media_type(f), bounds), "type": get_media_type(f),
             "name": f,
             "rev": int(os.path.getmtime(os.path.join(UPLOAD_FOLDER, f))) if os.path.exists(os.path.join(UPLOAD_FOLDER, f)) else 0,
             "groups": [g for g in get_media_groups(f, effective_cfg)
                        if is_group_active_on_screen(g, cfg, screen)]}
            for f in files
            if not is_media_disabled(f, effective_cfg) and is_media_scheduled(f, scfg)
        ])

    files = campaign_override.get('files', []) if campaign_override else get_all_media(cfg)
    return jsonify([
        {"path": _media_path(f, get_media_type(f), bounds), "type": get_media_type(f),
         "name": f,
         "rev": int(os.path.getmtime(os.path.join(UPLOAD_FOLDER, f))) if os.path.exists(os.path.join(UPLOAD_FOLDER, f)) else 0,
         "groups": [g for g in get_media_groups(f, cfg) if is_group_active_on_screen(g, cfg, '')]}
        for f in files
        if not is_media_disabled(f, cfg) and is_media_scheduled(f, cfg)
    ])


@bp.route('/api/durations')
def api_durations():
    guard = _screen_api_guard()
    if guard:
        return guard
    screen = request.args.get('screen', '').strip().lower()
    cfg    = load_config()
    if screen and screen in cfg.get('screens', {}):
        durations = dict(cfg.get("durations", {}))
        durations.update(cfg['screens'][screen].get('durations', {}))
        return jsonify(durations)
    return jsonify(cfg.get("durations", {}))


@bp.route('/api/pools')
def api_pools():
    guard = _screen_api_guard()
    if guard:
        return guard
    cfg = load_config()
    return jsonify(cfg.get('group_pools', {}))


@bp.route('/api/screens')
def api_screens():
    guard = _screen_api_guard()
    if guard:
        return guard
    cfg = load_config()
    return jsonify(list(cfg.get('screens', {}).keys()))


@bp.route('/api/halo')
def api_halo():
    guard = _screen_api_guard()
    if guard:
        return guard
    screen = request.args.get('screen', '').strip().lower()
    cfg = load_config()
    color = get_screen_halo_color(screen, cfg)
    return jsonify({
        'color': color,
        'rgb': halo_color_to_rgb(color),
    })

@bp.route('/api/diskusage')
def api_diskusage():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_disk_usage())


@bp.route('/api/client-heartbeat', methods=['POST'])
def api_client_heartbeat():
    data = request.get_json(silent=True) or {}
    if not os.environ.get('CLIENT_HEARTBEAT_TOKEN', '').strip():
        return jsonify({'ok': False, 'error': 'client_heartbeat_token_required'}), 403
    if not _heartbeat_token_is_valid(data):
        return jsonify({'ok': False, 'error': 'invalid_client_token'}), 403
    hostname = str(data.get('hostname') or '').strip()
    machine_id = hostname or str(data.get('machine_id') or '').strip()
    entry = record_client_heartbeat(
        machine_id=machine_id,
        hostname=hostname,
        client_name=data.get('client_name', ''),
        screen_name=data.get('screen_name', ''),
        ip_address=data.get('ip_address', ''),
        server_url=data.get('server_url', ''),
        client_version=data.get('client_version', ''),
        uptime_seconds=data.get('uptime_seconds'),
        cpu_load_percent=data.get('cpu_load_percent'),
        ram_used_mb=data.get('ram_used_mb'),
        ram_total_mb=data.get('ram_total_mb'),
        temperature_c=data.get('temperature_c'),
        disk_free_mb=data.get('disk_free_mb'),
        disk_total_mb=data.get('disk_total_mb'),
        resolution=data.get('resolution', ''),
        last_error=data.get('last_error', ''),
    )
    if entry is None:
        return jsonify({'ok': False, 'error': 'missing_machine_id'}), 400
    return jsonify({
        'ok': True,
        'machine_id': entry['machine_id'],
        'ip_address': entry['ip_address'],
        'last_seen': entry['last_seen'],
    })
