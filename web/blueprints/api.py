# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import secrets
from flask import Blueprint, request, jsonify
from redis import Redis

from services.config_svc import (
    get_screen_halo_color,
    halo_color_to_rgb,
    is_feature_enabled,
    load_config,
    normalize_screen_key,
    get_default_screen_name,
)
from services.clients_svc import record_client_heartbeat
from services.display_token_svc import screen_token_is_valid
from services.users_svc import is_admin, is_superadmin
from services.media_svc import (
    get_all_media, get_media_type, is_media_scheduled, get_disk_usage,
    is_media_disabled, get_media_groups, is_group_active_on_screen,
    get_media_url, get_original_media_url,
)
from services.playlist_cache_svc import (
    get_cached_playlist,
    make_config_revision,
    make_media_revision,
    make_playlist_revision,
)
from services.campaign_svc import resolve_campaign_override
from services.ephemeris_svc import ensure_ephemeride_image_async
from constants import UPLOAD_FOLDER

bp = Blueprint('api', __name__)

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
HEARTBEAT_RATE_LIMIT = 60
HEARTBEAT_RATE_WINDOW = 60

_redis: Redis = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL)
    return _redis


def _check_heartbeat_rate_limit():
    key = f"visio-display:rate-limit:heartbeat:{_client_ip()}"
    r = get_redis()
    count = r.incr(key)
    if count == 1:
        r.expire(key, HEARTBEAT_RATE_WINDOW)
    return int(count) <= HEARTBEAT_RATE_LIMIT


def _client_ip():
    return str(request.remote_addr or '').strip()


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


def _media_rev(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    return int(os.path.getmtime(path)) if os.path.exists(path) else 0


def _playlist_item(filename, cfg, screen, bounds):
    media_type = get_media_type(filename)
    return {
        "path": _media_path(filename, media_type, bounds),
        "type": media_type,
        "name": filename,
        "rev": _media_rev(filename),
        "groups": [
            group for group in get_media_groups(filename, cfg)
            if is_group_active_on_screen(group, cfg, screen)
        ],
    }


def _revision_token(revision):
    return "|".join(str(revision.get(key, "")) for key in ("config", "media", "time"))


def _assigned_playlist_files(cfg, screen_cfg):
    all_files = get_all_media(cfg)
    all_files_set = set(all_files)
    screen_order = screen_cfg.get('order', [])
    assigned = [f for f in screen_order if f in all_files_set]
    ephemeride_extras = [
        f for f in all_files
        if f.startswith('ephemeride_') and f not in screen_order
    ]
    return assigned + ephemeride_extras


def _build_images_playlist(cfg, screen, bounds, campaign_override):
    if screen and screen in cfg.get('screens', {}):
        scfg = cfg['screens'][screen]
        effective_cfg = dict(scfg)
        effective_cfg['groups'] = cfg.get('groups', {})
        effective_cfg['group_screens'] = cfg.get('group_screens', {})
        if campaign_override:
            files = campaign_override.get('files', [])
        else:
            files = _assigned_playlist_files(cfg, scfg)
        return [
            _playlist_item(f, effective_cfg, screen, bounds)
            for f in files
            if not is_media_disabled(f, effective_cfg) and is_media_scheduled(f, scfg)
        ]

    files = campaign_override.get('files', []) if campaign_override else _assigned_playlist_files(cfg, cfg)
    return [
        _playlist_item(f, cfg, '', bounds)
        for f in files
        if not is_media_disabled(f, cfg) and is_media_scheduled(f, cfg)
    ]


@bp.route('/api/config')
def api_config():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    cfg = load_config()
    if not is_superadmin():
        cfg = dict(cfg)
        backup_remote = cfg.get("backup_remote")
        if isinstance(backup_remote, dict) and backup_remote.get("password"):
            cfg["backup_remote"] = {**backup_remote, "password": ""}
    return jsonify(cfg)


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


@bp.route('/api/display-revision')
def api_display_revision():
    guard = _screen_api_guard()
    if guard:
        return guard
    cfg = load_config()
    revision = make_playlist_revision(cfg)
    return jsonify({
        **revision,
        "playlist": _revision_token(revision),
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
    bounds = _requested_display_bounds()
    cfg    = load_config()
    screen = normalize_screen_key(request.args.get('screen', ''), cfg)
    campaign_override = resolve_campaign_override(cfg, screen=screen)
    revision = make_playlist_revision(cfg)
    playlist = get_cached_playlist(
        ('api-images', screen, bounds),
        (make_config_revision(cfg), revision["time"]),
        make_media_revision(),
        lambda: _build_images_playlist(cfg, screen, bounds, campaign_override),
    )
    response = jsonify(playlist)
    response.headers["X-Visio-Playlist-Revision"] = _revision_token(revision)
    return response


@bp.route('/api/durations')
def api_durations():
    guard = _screen_api_guard()
    if guard:
        return guard
    cfg    = load_config()
    screen = normalize_screen_key(request.args.get('screen', ''), cfg)
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
    default_screen = get_default_screen_name(cfg)
    return jsonify(([default_screen] if default_screen else []) + list(cfg.get('screens', {}).keys()))


@bp.route('/api/halo')
def api_halo():
    guard = _screen_api_guard()
    if guard:
        return guard
    cfg = load_config()
    screen = normalize_screen_key(request.args.get('screen', ''), cfg)
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
    if not _check_heartbeat_rate_limit():
        return jsonify({'ok': False, 'error': 'rate_limited'}), 429
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
