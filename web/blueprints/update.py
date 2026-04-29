# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, redirect, render_template, request, session, url_for

from blueprints.guards import superadmin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path
from services.update_svc import get_update_status


bp = Blueprint("update", __name__)


@bp.route("/admin/update")
def update_page():
    redir = superadmin_guard()
    if redir:
        return redir

    return render_template(
        "admin_update.html",
        cfg=load_config(),
        current_user=session.get("user"),
        logo_path=get_logo_path(),
        update_status=get_update_status(fetch=True),
    )


@bp.route("/admin/update/check", methods=["POST"])
def check_update():
    redir = superadmin_guard()
    if redir:
        return redir

    return render_template(
        "admin_update.html",
        cfg=load_config(),
        current_user=session.get("user"),
        logo_path=get_logo_path(),
        update_status=get_update_status(fetch=True),
    )
