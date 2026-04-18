from flask import Blueprint, render_template, session

from blueprints.guards import admin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path

bp = Blueprint('wiki', __name__)


@bp.route('/admin/wiki')
def wiki_page():
    redir = admin_guard()
    if redir: return redir
    cfg = load_config()
    return render_template('admin_wiki.html',
        cfg=cfg,
        current_user=session.get('user'),
        logo_path=get_logo_path())
