# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import os
import uuid

from flask import Blueprint, redirect, jsonify, session

from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.activity_svc import log_activity, log_config_change
from services.users_svc import is_admin, is_superadmin
from services.config_svc import load_config, save_config
from services.queue_svc import (
    load_queue, save_queue,
    _rq_compress_job, _compress_q,
    is_encoding_window, get_queue_now, get_upload_jobs,
    get_redis,
)
from services.i18n import _flash
from blueprints.guards import admin_guard, superadmin_guard, perm_guard, feature_guard, feature_guard_json

bp = Blueprint('queue', __name__)


@bp.route('/admin/queue')
def admin_queue_view():
    redir = admin_guard()
    if redir: return redir
    g = feature_guard('videos')
    if g: return g
    g = feature_guard('compress')
    if g: return g
    return redirect('/admin/upload#encoding-queue')


@bp.route('/compress/<filename>', methods=['POST'])
def compress_video(filename):
    g = feature_guard_json('videos')
    if g: return g
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
    log_activity(session.get('user'), 'compress', filename=filename, details='compression en file')
    return jsonify({"ok": True, "job_id": job["id"]})


@bp.route('/queue/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    g = feature_guard_json('videos')
    if g: return g
    g = perm_guard('compress')
    if g: return g
    q   = load_queue()
    job = next((j for j in q if j['id'] == job_id), None)
    if not job:
        return jsonify({"error": "not found"}), 404
    if job['status'] == 'processing':
        return jsonify({"error": "cannot cancel"}), 400
    if job['status'] == 'pending':
        q.remove(job)
        save_queue(q)
        log_activity(session.get('user'), 'compress', filename=job['filename'], details='tâche annulée')
    else:
        cfg = load_config()
        hidden = cfg.get('hidden_recent_jobs', [])
        if job_id not in hidden:
            hidden.append(job_id)
            cfg['hidden_recent_jobs'] = hidden
            save_config(cfg)
            log_config_change(session.get('user'), f'job compression masqué:{job_id}')
    return jsonify({"ok": True})


@bp.route('/admin/queue/force', methods=['POST'])
def force_encode():
    g = superadmin_guard()
    if g: return g
    g = feature_guard('videos')
    if g: return g
    g = feature_guard('compress')
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
        log_activity(session.get('user'), 'compress', details=f'lancement forcé de {len(pending)} tâche(s)')
    _flash('flash_force_encode_started', 'success')
    return redirect('/admin/upload#encoding-queue')


@bp.route('/admin/compress/<filename>/force', methods=['POST'])
def force_compress_single(filename):
    g = feature_guard_json('videos')
    if g: return g
    g = feature_guard_json('compress')
    if g: return g
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
        log_activity(session.get('user'), 'compress', filename=filename, details='compression forcée')

    return jsonify({"ok": True, "job_id": job["id"]})


@bp.route('/api/queue')
def api_queue():
    g = feature_guard_json('videos')
    if g: return g
    g = feature_guard_json('compress')
    if g: return g
    if not is_admin():
        return jsonify({"error": "unauthorized"}), 401
    q = load_queue()
    cfg = load_config()
    hidden_recent = set(cfg.get('hidden_recent_jobs', []))
    active = [j for j in q if j['status'] in ('pending', 'processing')]
    recent = [j for j in q if j['status'] in ('done', 'error') and j['id'] not in hidden_recent][-5:]

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
        "now_hour":    get_queue_now().hour,
    })
