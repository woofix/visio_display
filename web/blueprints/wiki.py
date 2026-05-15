# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, render_template, session

from blueprints.guards import admin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path

bp = Blueprint('wiki', __name__)


@bp.route('/admin/wiki')
def wiki_page():
    return wiki_section_page('s1')


@bp.route('/admin/wiki/<section>')
def wiki_section_page(section='s1'):
    redir = admin_guard()
    if redir: return redir
    if section not in {f's{i}' for i in range(1, 24)}:
        section = 's1'
    cfg = load_config()
    return render_template('admin_wiki.html',
        cfg=cfg,
        wiki_section=section,
        current_user=session.get('user'),
        logo_path=get_logo_path())
