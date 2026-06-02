# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import logging
import os
import queue
import threading

from flask import Flask, Response, jsonify, request, stream_with_context

from services import update_svc


LOGGER = logging.getLogger(__name__)
ALLOWED_OPERATIONS = frozenset({
    "status",
    "runtime-status",
    "apply-update",
    "restart-stack",
    "apply-update-and-restart",
})


def create_app():
    app = Flask(__name__)

    @app.before_request
    def require_internal_token():
        if request.path == "/health":
            return None
        token = os.environ.get("UPDATER_API_TOKEN", "").strip()
        if not token:
            return jsonify({"ok": False, "error": "UPDATER_API_TOKEN non configuré."}), 503
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {token}":
            return jsonify({"ok": False, "error": "Accès updater refusé."}), 403
        return None

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "service": "visio-updater"})

    @app.get("/operations")
    def operations():
        return jsonify({"ok": True, "operations": sorted(ALLOWED_OPERATIONS)})

    @app.get("/status")
    def status():
        fetch_remote = request.args.get("fetch") == "1"
        try:
            status_payload = update_svc.get_update_status(fetch_remote=fetch_remote)
        except Exception as exc:
            LOGGER.exception("Updater status check failed fetch_remote=%s", fetch_remote)
            status_payload = update_svc._build_unavailable(
                update_svc.PUBLIC_UPDATER_UNAVAILABLE_MESSAGE,
                [],
                {"repo_dir": update_svc._repo_dir()},
            )
        return jsonify({"ok": True, "status": status_payload})

    @app.get("/runtime-status")
    def runtime_status():
        return jsonify({"ok": True, "runtime": update_svc.runtime_readiness_status()})

    @app.post("/apply-update")
    def apply_update():
        return _stream(update_svc.apply_update)

    @app.post("/restart-stack")
    def restart_stack():
        return _stream(update_svc.restart_stack)

    @app.post("/apply-update-and-restart")
    def apply_update_and_restart():
        return _stream(update_svc.apply_update_and_restart)

    return app


def _stream(operation):
    events = queue.Queue()
    done = threading.Event()

    def emit(event_type, **payload):
        events.put({"type": event_type, **payload})

    def progress(message):
        emit("log", message=message)

    def worker():
        try:
            result = operation(progress_callback=progress, lock_token=None)
            emit("done", status=result)
        except Exception as exc:
            LOGGER.exception("Updater streamed operation failed operation=%s", getattr(operation, "__name__", "unknown"))
            emit("error", message=update_svc.PUBLIC_UPDATER_UNAVAILABLE_MESSAGE)
        finally:
            done.set()

    threading.Thread(target=worker, daemon=True).start()

    @stream_with_context
    def generate():
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload, ensure_ascii=True) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("UPDATER_PORT", "8090")))
