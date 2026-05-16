# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import queue
import threading

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session, stream_with_context

from blueprints.guards import superadmin_guard
from services.activity_svc import log_config_change
from services.config_svc import load_config
from services.media_svc import get_logo_path
from services.system_lock_svc import (
    SystemTaskAlreadyRunning,
    acquire_lock,
    release_lock,
    get_system_status,
    update_lock,
)
from services.i18n import _t
from services.update_svc import UPDATE_STEPS, apply_update_and_restart, get_update_status, runtime_readiness_status


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


@bp.route("/admin/version/update/runtime-status")
def update_runtime_status():
    redir = superadmin_guard()
    if redir:
        return jsonify({"ok": False, "error": "forbidden"}), 403
    system = get_system_status()
    runtime = runtime_readiness_status()
    if (
        request.args.get("complete") == "1"
        and runtime.get("ready")
        and system.get("active")
        and system.get("type") in {"reboot", "update"}
    ):
        release_lock(force=True)
        system = get_system_status()
    return jsonify({
        "ok": True,
        "system": system,
        "runtime": runtime,
    })


def _stream_operation(operation, *, activity_message, task_type, start_message, keep_lock_after_success=False):
    redir = superadmin_guard()
    if redir:
        return jsonify({"ok": False, "error": "forbidden"}), 403

    try:
        initial_steps = [
            {"key": key, "label": _t(label_key), "state": "active" if index == 0 else "pending"}
            for index, (key, label_key) in enumerate(UPDATE_STEPS)
        ] if task_type == "update" else None
        lock_token = acquire_lock(
            task_type,
            start_message,
            progress=5,
            stage="pull" if task_type == "update" else None,
            steps=initial_steps,
        )
    except SystemTaskAlreadyRunning as exc:
        return jsonify({"ok": False, "error": str(exc) or _t("system_lock_title")}), 409

    app = current_app._get_current_object()
    username = session.get("user")
    events = queue.Queue()
    done = threading.Event()
    successful = threading.Event()
    lock_timeout = 600 if task_type == "reboot" else 1800

    def emit(event_type, **payload):
        events.put({"type": event_type, **payload})

    def progress(message):
        emit("log", message=message)
        update_lock(lock_token, message=message or start_message, timeout_seconds=lock_timeout)

    def worker():
        try:
            with app.app_context():
                result = operation(progress_callback=progress, lock_token=lock_token)
                log_config_change(username, activity_message)
            emit("done", status=result)
            successful.set()
        except Exception as exc:
            emit("error", message=str(exc) or exc.__class__.__name__)
        finally:
            if not keep_lock_after_success or not successful.is_set():
                release_lock(lock_token)
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield json.dumps({"type": "log", "message": start_message}) + "\n"
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@bp.route("/admin/version/update/apply-stream", methods=["POST"])
def apply_update_stream():
    return _stream_operation(
        apply_update_and_restart,
        activity_message="server update applied",
        task_type="update",
        start_message=_t("version_apply_start"),
        keep_lock_after_success=True,
    )
