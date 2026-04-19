import os
import uuid
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, jsonify, session

from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.users_svc import load_users, is_admin, is_superadmin
from services.queue_svc import (
    load_queue, save_queue,
    _rq_compress_job, _compress_q,
    is_encoding_window, get_upload_jobs,
    get_redis,
)
from services.media_svc import get_logo_path
from services.i18n import _flash
from blueprints.guards import admin_guard, superadmin_guard, perm_guard, feature_guard_json

bp = Blueprint('queue', __name__)


@bp.route('/admin/queue')
def admin_queue_view():
    redir = admin_guard()
    if redir: return redir
    users = load_users()
    return render_template('admin_queue.html',
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path())


@bp.route('/compress/<filename>', methods=['POST'])
def compress_video(filename):
    g = perm_guard('compress')
    if g: return g
    g = feature_guard_json('compress')
    if g: return g
    filename = os.path.basename(filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in VIDEO_EXTS:
        return jsonify({"error": "not a video"}), 400
    if not os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        return jsonify({"error": "not found"}), 404
    q = load_queue()
    if any(j['filename'] == filename and j['status'] in ('pending', 'processing') for j in q):
        return jsonify({"error": "already queued"}), 409
    job = {
        "id":       str(uuid.uuid4())[:8],
        "filename": filename,
        "status":   "pending",
        "added":    datetime.now().isoformat(),
        "started":  None,
        "finished": None,
    }
    q.append(job)
    save_queue(q)
    return jsonify({"ok": True, "job_id": job["id"]})


@bp.route('/queue/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    g = perm_guard('compress')
    if g: return g
    q   = load_queue()
    job = next((j for j in q if j['id'] == job_id), None)
    if not job:
        return jsonify({"error": "not found"}), 404
    if job['status'] == 'processing':
        return jsonify({"error": "cannot cancel"}), 400
    q.remove(job)
    save_queue(q)
    return jsonify({"ok": True})


@bp.route('/admin/queue/force', methods=['POST'])
def force_encode():
    g = superadmin_guard()
    if g: return g
    q       = load_queue()
    pending = [j for j in q if j['status'] == 'pending']
    for job in pending:
        job['status']  = 'processing'
        job['started'] = datetime.now().isoformat()
    if pending:
        save_queue(q)
        for job in pending:
            _compress_q().enqueue(_rq_compress_job, job['id'], job_timeout=3600)
    _flash('flash_force_encode_started', 'success')
    return redirect(url_for('queue.admin_queue_view'))


@bp.route('/admin/compress/<filename>/force', methods=['POST'])
def force_compress_single(filename):
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    if not is_superadmin():
        return jsonify({"error": "permission denied"}), 403
    filename = os.path.basename(filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in VIDEO_EXTS:
        return jsonify({"error": "not a video"}), 400
    if not os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        return jsonify({"error": "not found"}), 404

    q        = load_queue()
    existing = next((j for j in q if j['filename'] == filename
                     and j['status'] in ('pending', 'processing')), None)
    if existing:
        job = existing
    else:
        job = {
            "id":       str(uuid.uuid4())[:8],
            "filename": filename,
            "status":   "pending",
            "added":    datetime.now().isoformat(),
            "started":  None,
            "finished": None,
        }
        q.append(job)
        save_queue(q)

    if job['status'] == 'pending':
        job['status']  = 'processing'
        job['started'] = datetime.now().isoformat()
        save_queue(q)
        _compress_q().enqueue(_rq_compress_job, job['id'], job_timeout=3600)

    return jsonify({"ok": True, "job_id": job["id"]})


@bp.route('/api/queue')
def api_queue():
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    q      = load_queue()
    active = [j for j in q if j['status'] in ('pending', 'processing')]
    recent = [j for j in q if j['status'] in ('done', 'error')][-5:]

    # Attach compress progress from Redis for processing jobs
    r = get_redis()
    for j in active:
        if j['status'] == 'processing':
            pct = r.get(f'visio-display:progress:{j["id"]}')
            if pct is not None:
                j['progress'] = int(pct)

    return jsonify({
        "active":      active,
        "recent":      recent,
        "upload_jobs": get_upload_jobs(),
        "window":      is_encoding_window(),
        "now_hour":    datetime.now().hour,
    })
