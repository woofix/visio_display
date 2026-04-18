from flask import Blueprint, render_template, session

from services.users_svc import load_users
from services.config_svc import load_config
from services.media_svc import get_all_media, get_disk_usage, get_logo_path
from blueprints.guards import admin_guard

bp = Blueprint('admin', __name__)


@bp.route('/admin')
def admin_page():
    redir = admin_guard()
    if redir: return redir
    cfg   = load_config()
    files = get_all_media()
    disk  = get_disk_usage()
    users = load_users()
    return render_template('admin_dashboard.html',
        files=files, cfg=cfg, disk=disk,
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path())
