from flask import Blueprint, request, jsonify

from services.config_svc import load_config
from services.media_svc import (
    get_all_media, get_file_info, is_media_scheduled, get_disk_usage,
    is_media_disabled, get_media_groups, is_group_active_on_screen,
)
from services.ephemeris_svc import generate_ephemeride_image
from constants import UPLOAD_FOLDER, MEDIA_EXTS
import os

bp = Blueprint('api', __name__)


@bp.route('/api/config')
def api_config():
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

    if screen and screen in cfg.get('screens', {}):
        scfg      = cfg['screens'][screen]
        effective_cfg = dict(scfg)
        effective_cfg['groups'] = cfg.get('groups', {})
        effective_cfg['group_screens'] = cfg.get('group_screens', {})
        all_files = {f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(MEDIA_EXTS)}
        files     = [f for f in scfg.get('order', []) if f in all_files]
        return jsonify([
            {"path": f"/static/data/{f}", "type": get_file_info(f)["type"],
             "groups": [g for g in get_media_groups(f, effective_cfg)
                        if is_group_active_on_screen(g, cfg, screen)]}
            for f in files
            if not is_media_disabled(f, effective_cfg) and is_media_scheduled(f, scfg)
        ])

    files    = get_all_media()
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
        return jsonify(cfg['screens'][screen].get('durations', {}))
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
    return jsonify(get_disk_usage())
