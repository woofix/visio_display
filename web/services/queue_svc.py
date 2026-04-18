import os
import subprocess
import threading
import time
import uuid
from datetime import datetime

from redis import Redis
from rq import Queue, get_current_job
from rq.job import Job
from rq.registry import StartedJobRegistry

from constants import UPLOAD_FOLDER
from services.config_svc import load_config, save_config
from services.i18n import _t

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

_redis: Redis = None
_flask_app = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL)
    return _redis


def _upload_q() -> Queue:
    return Queue('ramses:upload', connection=get_redis())


def _compress_q() -> Queue:
    return Queue('ramses:compress', connection=get_redis())


def _get_worker_app():
    """Returns Flask app for use inside RQ worker tasks."""
    global _flask_app
    if _flask_app is not None:
        return _flask_app
    # Worker process: create app without starting the scheduler thread
    from app import create_app
    _flask_app = create_app(start_scheduler=False)
    return _flask_app


def load_queue():
    from db import EncodeJob
    return [j.to_dict() for j in EncodeJob.query.order_by(EncodeJob.added).all()]


def save_queue(q):
    from db import db, EncodeJob

    incoming_ids = {job['id'] for job in q}
    existing_ids = {j.id for j in EncodeJob.query.with_entities(EncodeJob.id).all()}

    for job_id in existing_ids - incoming_ids:
        EncodeJob.query.filter_by(id=job_id).delete()

    for job in q:
        row = db.session.get(EncodeJob, job['id'])
        if row is None:
            row = EncodeJob(id=job['id'], filename=job['filename'],
                            status=job['status'], added=job['added'])
            db.session.add(row)
        row.status    = job['status']
        row.started   = job.get('started')
        row.finished  = job.get('finished')
        row.new_name  = job.get('new_name')
        row.before_mb = job.get('before')
        row.after_mb  = job.get('after')
        row.ratio     = job.get('ratio')
        row.message   = job.get('message')

    db.session.commit()


def is_encoding_window():
    h = datetime.now().hour
    return h >= 22 or h < 6


def _get_video_duration_ms(path):
    import json as _json
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path
        ], capture_output=True, text=True, check=True)
        info     = _json.loads(result.stdout)
        duration = float(info.get('format', {}).get('duration', 0))
        return int(duration * 1000)
    except Exception:
        return 0


def _reencode_with_progress(src, dst, compress, job_id):
    crf    = '28' if compress else '26'
    preset = 'veryfast' if compress else 'ultrafast'
    vf     = 'scale=trunc(iw/2)*2:trunc(ih/2)*2'
    audio  = '96k' if compress else '128k'
    duration_ms = _get_video_duration_ms(src)
    cmd = [
        'ffmpeg', '-i', src,
        '-vcodec', 'libx264', '-crf', crf, '-preset', preset,
        '-acodec', 'aac', '-b:a', audio,
        '-movflags', '+faststart', '-vf', vf,
        '-progress', 'pipe:1', '-nostats',
        '-y', dst
    ]
    rq_job = get_current_job()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in proc.stdout:
            if line.startswith('out_time_ms=') and duration_ms > 0:
                try:
                    ms  = int(line.strip().split('=')[1])
                    pct = min(99, int(ms / duration_ms * 100))
                    # Store in RQ job meta (readable cross-process via Redis)
                    if rq_job:
                        rq_job.meta['progress'] = pct
                        rq_job.save_meta()
                    # Also store in a Redis key so Flask can poll compress jobs
                    get_redis().set(f'ramses:progress:{job_id}', pct, ex=3600)
                except (ValueError, ZeroDivisionError):
                    pass
        proc.wait()
        ok = proc.returncode == 0
        if rq_job:
            rq_job.meta['progress'] = 100 if ok else -1
            rq_job.meta['status']   = 'done' if ok else 'error'
            rq_job.save_meta()
        get_redis().delete(f'ramses:progress:{job_id}')
        return ok
    except Exception as e:
        print(f"[FFMPEG ERROR] {e}")
        if rq_job:
            rq_job.meta['status']   = 'error'
            rq_job.meta['progress'] = -1
            rq_job.save_meta()
        return False


# ── RQ tasks ────────────────────────────────────────────────────────────────

def _rq_upload_encode(job_id, src_tmp, dest, final_name):
    """RQ task: re-encode an uploaded video, then add it to the compress queue."""
    rq_job = get_current_job()
    if rq_job:
        rq_job.meta.update({'filename': final_name, 'status': 'processing', 'progress': 0})
        rq_job.save_meta()

    ok = _reencode_with_progress(src_tmp, dest, compress=False, job_id=job_id)
    try:
        os.remove(src_tmp)
    except Exception:
        pass

    with _get_worker_app().app_context():
        if ok:
            cfg = load_config()
            if final_name not in cfg.get('disabled', []):
                cfg.setdefault('disabled', []).append(final_name)
                save_config(cfg)
            q = load_queue()
            if not any(j['filename'] == final_name and j['status'] in ('pending', 'processing') for j in q):
                q.append({
                    "id":       str(uuid.uuid4())[:8],
                    "filename": final_name,
                    "status":   "pending",
                    "added":    datetime.now().isoformat(),
                    "started":  None,
                    "finished": None,
                })
                save_queue(q)
        else:
            try:
                os.remove(dest)
            except Exception:
                pass


def _rq_compress_job(encode_job_id):
    """RQ task: compress a queued video file."""
    with _get_worker_app().app_context():
        q   = load_queue()
        job = next((j for j in q if j['id'] == encode_job_id), None)
        if not job:
            return

        src = os.path.join(UPLOAD_FOLDER, job['filename'])
        if not os.path.exists(src):
            job['status']   = 'error'
            job['message']  = _t('file_not_found_internal')
            job['finished'] = datetime.now().isoformat()
            save_queue(q)
            return

        size_before = os.path.getsize(src)
        tmp = src + '.compress_tmp.mp4'
        out = os.path.splitext(src)[0] + '.mp4'

        ok = _reencode_with_progress(src, tmp, compress=True, job_id=encode_job_id)
        if ok:
            os.replace(tmp, out)
            if out != src:
                try:
                    os.remove(src)
                except Exception:
                    pass
            size_after = os.path.getsize(out)
            new_name   = os.path.basename(out)
            job['status']   = 'done'
            job['new_name'] = new_name
            job['before']   = round(size_before / 1024 / 1024, 1)
            job['after']    = round(size_after  / 1024 / 1024, 1)
            job['ratio']    = round(size_before / size_after, 1) if size_after else '?'
            cfg = load_config()
            if new_name != job['filename']:
                for key in ('order', 'disabled'):
                    lst = cfg.get(key, [])
                    if job['filename'] in lst:
                        lst[lst.index(job['filename'])] = new_name
                        cfg[key] = lst
                if job['filename'] in cfg.get('durations', {}):
                    cfg['durations'][new_name] = cfg['durations'].pop(job['filename'])
                if job['filename'] in cfg.get('groups', {}):
                    cfg['groups'][new_name] = cfg['groups'].pop(job['filename'])
                if job['filename'] in cfg.get('schedules', {}):
                    cfg['schedules'][new_name] = cfg['schedules'].pop(job['filename'])
                for screen_cfg in cfg.get('screens', {}).values():
                    for key in ('order', 'disabled'):
                        lst = screen_cfg.get(key, [])
                        if job['filename'] in lst:
                            lst[lst.index(job['filename'])] = new_name
                            screen_cfg[key] = lst
                    if job['filename'] in screen_cfg.get('durations', {}):
                        screen_cfg['durations'][new_name] = screen_cfg['durations'].pop(job['filename'])
                    if job['filename'] in screen_cfg.get('schedules', {}):
                        screen_cfg['schedules'][new_name] = screen_cfg['schedules'].pop(job['filename'])
            disabled = cfg.get('disabled', [])
            if new_name in disabled:
                disabled.remove(new_name)
                cfg['disabled'] = disabled
            save_config(cfg)
        else:
            try:
                os.remove(tmp)
            except Exception:
                pass
            job['status']  = 'error'
            job['message'] = _t('ffmpeg_failed')

        job['finished'] = datetime.now().isoformat()
        save_queue(q)


# ── Scheduler thread (replaces _encoder_loop) ────────────────────────────────

def _scheduler_loop():
    """Thread: enqueues one pending compress job per cycle during the time window."""
    time.sleep(10)
    while True:
        time.sleep(60)
        if not is_encoding_window():
            continue
        # Redis NX lock prevents multiple gunicorn workers from scheduling simultaneously
        if not get_redis().set('ramses:scheduler_lock', 1, nx=True, ex=90):
            continue
        try:
            with _flask_app.app_context():
                q   = load_queue()
                job = next((j for j in q if j['status'] == 'pending'), None)
                if not job:
                    continue
                job['status']  = 'processing'
                job['started'] = datetime.now().isoformat()
                save_queue(q)
                _compress_q().enqueue(_rq_compress_job, job['id'], job_timeout=3600)
        except Exception as e:
            print(f"[SCHEDULER] {e}")


def start_encoder_thread(app):
    global _flask_app
    _flask_app = app
    threading.Thread(target=_scheduler_loop, daemon=True).start()


# ── Upload job API ────────────────────────────────────────────────────────────

def enqueue_upload_job(src_tmp, dest, final_name):
    """Enqueue a video upload re-encode job. Returns the RQ job ID."""
    job_id = str(uuid.uuid4())[:8]
    rq_job = _upload_q().enqueue(
        _rq_upload_encode,
        job_id, src_tmp, dest, final_name,
        job_timeout=1800,
        meta={'filename': final_name, 'status': 'queued', 'progress': 0},
    )
    return rq_job.id


def get_upload_jobs():
    """Returns a list of in-progress/queued upload encode jobs with their progress."""
    q      = _upload_q()
    result = []

    registry = StartedJobRegistry(queue=q)
    for jid in registry.get_job_ids():
        try:
            j = Job.fetch(jid, connection=get_redis())
            if j.meta.get('filename'):
                result.append({
                    'filename': j.meta['filename'],
                    'status':   'processing',
                    'progress': j.meta.get('progress', 0),
                })
        except Exception:
            pass

    for jid in q.job_ids:
        try:
            j = Job.fetch(jid, connection=get_redis())
            if j.meta.get('filename'):
                result.append({
                    'filename': j.meta['filename'],
                    'status':   'queued',
                    'progress': 0,
                })
        except Exception:
            pass

    return result
