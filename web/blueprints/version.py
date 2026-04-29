# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, render_template, session

from blueprints.guards import superadmin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path
from services.version_svc import get_version_status


bp = Blueprint("version", __name__)


@bp.route("/admin/version")
def version_page():
    redir = superadmin_guard()
    if redir:
        return redir

    return render_template(
        "admin_version.html",
        cfg=load_config(),
        current_user=session.get("user"),
        logo_path=get_logo_path(),
        version_status=get_version_status(),
    )
