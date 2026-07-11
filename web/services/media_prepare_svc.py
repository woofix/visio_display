# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import logging

from flask import has_app_context
from rq import get_current_job

from services.media_svc import prepare_media_derivatives
from services.playlist_cache_svc import bump_media_revision
from services.queue_svc import _get_worker_app, _upload_q

logger = logging.getLogger(__name__)


def _rq_prepare_media(filename):
    rq_job = get_current_job()
    if rq_job:
        rq_job.meta.update({"filename": filename, "status": "processing", "progress": 0, "type": "media_prepare"})
        rq_job.save_meta()

    if has_app_context():
        ok = prepare_media_derivatives(filename)
        bump_media_revision()
    else:
        with _get_worker_app().app_context():
            ok = prepare_media_derivatives(filename)
            bump_media_revision()

    if rq_job:
        rq_job.meta["status"] = "done" if ok else "error"
        rq_job.meta["progress"] = 100 if ok else -1
        rq_job.save_meta()
    if not ok:
        logger.warning("Media preparation failed in worker: %s", filename)
    return ok


def enqueue_media_prepare_job(filename):
    try:
        job = _upload_q().enqueue(
            _rq_prepare_media,
            filename,
            job_timeout=1800,
            meta={"filename": filename, "status": "queued", "progress": 0, "type": "media_prepare"},
        )
        logger.info("Media preparation queued: %s", filename)
        return getattr(job, "id", None)
    except Exception as exc:
        logger.warning("Media preparation queue unavailable for %s: %s", filename, exc)
        return None
