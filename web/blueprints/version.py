# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import queue
import threading

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session, stream_with_context

from blueprints.guards import superadmin_guard
from services.activity_svc import log_config_change
from services.config_svc import load_config
from services.media_svc import get_logo_path
from services.update_svc import apply_update, get_update_status, restart_stack


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
        update_status=get_update_status(fetch_remote=False),
    )


@bp.route("/admin/version/update/status")
def update_status():
    redir = superadmin_guard()
    if redir:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    return jsonify({"ok": True, "status": get_update_status(fetch_remote=request.args.get("fetch") == "1")})


def _stream_operation(operation, *, activity_message):
    redir = superadmin_guard()
    if redir:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    app = current_app._get_current_object()
    username = session.get("user")
    events = queue.Queue()
    done = threading.Event()

    def emit(event_type, **payload):
        events.put({"type": event_type, **payload})

    def worker():
        try:
            with app.app_context():
                result = operation(progress_callback=lambda message: emit("log", message=message))
                log_config_change(username, activity_message)
            emit("done", status=result)
        except Exception as exc:
            emit("error", message=str(exc) or exc.__class__.__name__)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield json.dumps({"type": "log", "message": "Préparation..."}) + "\n"
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@bp.route("/admin/version/update/apply-stream", methods=["POST"])
def apply_update_stream():
    return _stream_operation(apply_update, activity_message="server update applied")


@bp.route("/admin/version/update/restart-stream", methods=["POST"])
def restart_update_stream():
    return _stream_operation(restart_stack, activity_message="docker stack restarted after update")
