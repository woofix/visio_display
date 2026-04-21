from flask import Blueprint, render_template, session

from services.users_svc import load_users
from services.config_svc import load_config
from services.media_svc import get_all_media, get_disk_usage, get_logo_path
from services.campaign_svc import get_campaigns, serialize_campaign_for_view
from blueprints.guards import admin_guard

bp = Blueprint('admin', __name__)


@bp.route('/admin')
def admin_page():
    redir = admin_guard()
    if redir: return redir
    cfg     = load_config()
    files   = get_all_media()
    disk    = get_disk_usage()
    users   = load_users()
    screens = list(cfg.get('screens', {}).keys())
    active_campaigns = []
    for campaign in get_campaigns(cfg):
        serialized = serialize_campaign_for_view(campaign, cfg)
        if serialized.get('is_active'):
            active_campaigns.append(serialized)
    return render_template('admin_dashboard.html',
        files=files, cfg=cfg, disk=disk, screens=screens,
        active_campaigns=active_campaigns,
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path())
