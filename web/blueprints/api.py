# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import os
import secrets
from flask import Blueprint, request, jsonify

from services.config_svc import load_config
from services.clients_svc import record_client_heartbeat
from services.users_svc import is_admin
from services.media_svc import (
    get_all_media, get_file_info, is_media_scheduled, get_disk_usage,
    is_media_disabled, get_media_groups, is_group_active_on_screen,
)
from services.campaign_svc import resolve_campaign_override
from services.ephemeris_svc import generate_ephemeride_image
from constants import UPLOAD_FOLDER, MEDIA_EXTS

bp = Blueprint('api', __name__)


def _best_remote_ip():
    if request.access_route:
        return str(request.access_route[0]).strip()
    return str(request.remote_addr or '').strip()


def _heartbeat_token_is_valid(data):
    expected = os.environ.get('CLIENT_HEARTBEAT_TOKEN', '').strip()
    if not expected:
        return True
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
    alert = load_config().get('priority_alert', {})
    return jsonify({
        'message': str(alert.get('message', '') or ''),
        'updated_at': alert.get('updated_at'),
    })


@bp.route('/api/images')
def get_images():
    generate_ephemeride_image()
    screen = request.args.get('screen', '').strip().lower()
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
            all_files = {f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(MEDIA_EXTS)}
            files = [f for f in scfg.get('order', []) if f in all_files]
        return jsonify([
            {"path": f"/static/data/{f}", "type": get_file_info(f)["type"],
             "groups": [g for g in get_media_groups(f, effective_cfg)
                        if is_group_active_on_screen(g, cfg, screen)]}
            for f in files
            if not is_media_disabled(f, effective_cfg) and is_media_scheduled(f, scfg)
        ])

    files = campaign_override.get('files', []) if campaign_override else get_all_media()
    return jsonify([
        {"path": f"/static/data/{f}", "type": get_file_info(f)["type"],
         "groups": get_media_groups(f, cfg)}
        for f in files
        if not is_media_disabled(f, cfg) and is_media_scheduled(f, cfg)
    ])


@bp.route('/api/durations')
def api_durations():
    screen = request.args.get('screen', '').strip().lower()
    cfg    = load_config()
    if screen and screen in cfg.get('screens', {}):
        durations = dict(cfg.get("durations", {}))
        durations.update(cfg['screens'][screen].get('durations', {}))
        return jsonify(durations)
    return jsonify(cfg.get("durations", {}))


@bp.route('/api/pools')
def api_pools():
    cfg = load_config()
    return jsonify(cfg.get('group_pools', {}))


@bp.route('/api/screens')
def api_screens():
    cfg = load_config()
    return jsonify(list(cfg.get('screens', {}).keys()))


@bp.route('/api/diskusage')
def api_diskusage():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(get_disk_usage())


@bp.route('/api/client-heartbeat', methods=['POST'])
def api_client_heartbeat():
    data = request.get_json(silent=True) or {}
    if not _heartbeat_token_is_valid(data):
        return jsonify({'ok': False, 'error': 'invalid_client_token'}), 403
    hostname = str(data.get('hostname') or '').strip()
    machine_id = hostname or str(data.get('machine_id') or '').strip()
    entry = record_client_heartbeat(
        machine_id=machine_id,
        hostname=hostname,
        client_name=data.get('client_name', ''),
        screen_name=data.get('screen_name', ''),
        ip_address=_best_remote_ip(),
        server_url=data.get('server_url', ''),
    )
    if entry is None:
        return jsonify({'ok': False, 'error': 'missing_machine_id'}), 400
    return jsonify({
        'ok': True,
        'machine_id': entry['machine_id'],
        'ip_address': entry['ip_address'],
        'last_seen': entry['last_seen'],
    })
