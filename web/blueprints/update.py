# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import time

from flask import Blueprint, Response, jsonify, render_template, session, stream_with_context

from blueprints.guards import admin_guard_json, superadmin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path
from services.update_svc import (
    get_runtime_update_state,
    get_update_status,
    read_update_logs,
    start_update,
)


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


@bp.route("/api/update", methods=["GET"])
def api_update_status():
    redir = admin_guard_json()
    if redir:
        return redir
    state = get_runtime_update_state()
    state["version"] = get_update_status(fetch=True)
    return jsonify(state)


@bp.route("/api/update", methods=["POST"])
def api_update_start():
    redir = admin_guard_json()
    if redir:
        return redir
    payload, status_code = start_update()
    return jsonify(payload), status_code


@bp.route("/api/update/stream")
def api_update_stream():
    redir = admin_guard_json()
    if redir:
        return redir

    def events():
        sent = ""
        last_status = ""
        for _ in range(7200):
            state = get_runtime_update_state()
            logs = read_update_logs()
            payload = {
                "status": state.get("status", "idle"),
                "message": state.get("message", ""),
                "logs": logs,
            }
            encoded = json.dumps(payload, ensure_ascii=False)
            if encoded != sent or payload["status"] != last_status:
                sent = encoded
                last_status = payload["status"]
                yield f"data: {encoded}\n\n"
            if payload["status"] in {"success", "error", "idle"}:
                break
            time.sleep(1)

    response = Response(stream_with_context(events()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
