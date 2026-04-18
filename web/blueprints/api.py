from flask import Blueprint, request, jsonify

from services.config_svc import load_config
from services.media_svc import get_all_media, get_file_info, is_media_scheduled, get_disk_usage
from services.ephemeris_svc import generate_ephemeride_image
from constants import UPLOAD_FOLDER, MEDIA_EXTS
import os

bp = Blueprint('api', __name__)


@bp.route('/api/config')
def api_config():
    return jsonify(load_config())


@bp.route('/api/images')
def get_images():
    generate_ephemeride_image()
    screen = request.args.get('screen', '').strip().lower()
    cfg    = load_config()

    if screen and screen in cfg.get('screens', {}):
        scfg      = cfg['screens'][screen]
        disabled  = scfg.get('disabled', [])
        all_files = {f for f in os.listdir(UPLOAD_FOLDER) if f.lower().endswith(MEDIA_EXTS)}
        files     = [f for f in scfg.get('order', []) if f in all_files]
        return jsonify([
            {"path": f"/static/data/{f}", "type": get_file_info(f)["type"]}
            for f in files
            if f not in disabled and is_media_scheduled(f, scfg)
        ])

    disabled = cfg.get("disabled", [])
    files    = get_all_media()
    return jsonify([
        {"path": f"/static/data/{f}", "type": get_file_info(f)["type"]}
        for f in files
        if f not in disabled and is_media_scheduled(f, cfg)
    ])


@bp.route('/api/durations')
def api_durations():
    screen = request.args.get('screen', '').strip().lower()
    cfg    = load_config()
    if screen and screen in cfg.get('screens', {}):
        return jsonify(cfg['screens'][screen].get('durations', {}))
    return jsonify(cfg.get("durations", {}))


@bp.route('/api/diskusage')
def api_diskusage():
    return jsonify(get_disk_usage())
