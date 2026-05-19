# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import subprocess

from flask import jsonify, redirect, url_for
from PIL import Image

import constants as C
from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.activity_svc import log_activity
from services.config_svc import load_config, save_config
from services.i18n import _flash, _t
from services.media_svc import (
    are_videos_enabled,
    clean_filename,
    delete_image_variants,
    delete_media_thumbnail,
    delete_video_variants,
    generate_standard_renditions,
    get_video_dimensions,
    is_valid_uploaded_image,
)
from services.playlist_cache_svc import bump_media_revision
from services.queue_svc import enqueue_compress_job

MAX_FILE_UPLOAD_SIZE = getattr(C, "MAX_FILE_UPLOAD_SIZE", 150 * 1024 * 1024)
MAX_BATCH_UPLOAD_SIZE = getattr(C, "MAX_BATCH_UPLOAD_SIZE", 256 * 1024 * 1024)
MAX_UPLOAD_PDF_PAGES = max(1, getattr(C, "MAX_UPLOAD_PDF_PAGES", 80))
MAX_UPLOAD_IMAGE_PIXELS = max(1, getattr(C, "MAX_UPLOAD_IMAGE_PIXELS", 50_000_000))
MAX_UPLOAD_VIDEO_SECONDS = max(1, getattr(C, "MAX_UPLOAD_VIDEO_SECONDS", 3 * 60 * 60))
MEDIA_PROBE_TIMEOUT_SECONDS = max(1, getattr(C, "MEDIA_PROBE_TIMEOUT_SECONDS", 15))
MEDIA_CONVERT_TIMEOUT_SECONDS = max(1, getattr(C, "MEDIA_CONVERT_TIMEOUT_SECONDS", 120))
ALLOWED_UPLOAD_EXTS = VIDEO_EXTS + (".pdf", ".jpg", ".jpeg", ".png")


class UploadValidationError(ValueError):
    def __init__(self, error, status_code=400, **payload):
        super().__init__(error)
        self.error = error
        self.status_code = status_code
        self.payload = {"error": error, **payload}


def get_uploaded_file_size(file_storage):
    stream = getattr(file_storage, "stream", None)
    if stream is None:
        return 0
    try:
        current = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current)
        return size
    except (AttributeError, OSError):
        return 0


def normalize_conflict_strategy(raw_value):
    value = str(raw_value or "").strip().lower()
    return value if value in {"rename_custom", "overwrite"} else ""


def load_rename_map(form_data):
    try:
        payload = json.loads(form_data.get("rename_map", "{}") or "{}")
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(source).strip(): clean_filename(str(target))
        for source, target in payload.items()
        if str(source).strip() and clean_filename(str(target))
    }


def pdf_page_filenames(filename):
    stem = os.path.splitext(filename)[0]
    page = 1
    pages = []
    while True:
        page_filename = f"{stem}_page_{page}.jpg"
        if not os.path.exists(os.path.join(UPLOAD_FOLDER, page_filename)):
            break
        pages.append(page_filename)
        page += 1
    return pages


def collect_upload_name_conflicts(files):
    conflicts = []
    seen = set()
    for index, file in enumerate(files):
        if not file or not file.filename:
            continue
        filename = clean_filename(file.filename)
        if not filename:
            continue
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".pdf":
            existing_pages = pdf_page_filenames(filename)
            path_exists = bool(existing_pages)
        else:
            path_exists = os.path.exists(os.path.join(UPLOAD_FOLDER, filename))
        duplicate_in_batch = filename in seen
        if path_exists or duplicate_in_batch:
            conflicts.append({
                "upload_index": index,
                "filename": filename,
            })
        seen.add(filename)
    return conflicts


def prepare_overwrite_target(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        stem = os.path.splitext(filename)[0]
        page = 1
        while True:
            page_filename = f"{stem}_page_{page}.jpg"
            page_path = os.path.join(UPLOAD_FOLDER, page_filename)
            if not os.path.exists(page_path):
                break
            delete_media_thumbnail(page_filename)
            delete_image_variants(page_filename)
            os.remove(page_path)
            page += 1
    else:
        path = os.path.join(UPLOAD_FOLDER, filename)
        delete_media_thumbnail(filename)
        delete_image_variants(filename)
        delete_video_variants(filename)
        if os.path.exists(path):
            os.remove(path)


def resolve_custom_rename(file_index, filename, rename_map):
    target = rename_map.get(str(file_index), "")
    if not target:
        return None, "missing rename"
    source_ext = os.path.splitext(filename)[1].lower()
    target_root, target_ext = os.path.splitext(target)
    if not target_ext:
        target = f"{target_root}{source_ext}"
        target_ext = source_ext
    if target_ext.lower() != source_ext:
        return None, "extension mismatch"
    return target, None


def has_supported_extension(filename, *, videos_enabled=True):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTS:
        return False
    if ext in VIDEO_EXTS and not videos_enabled:
        return False
    return True


def validate_image_dimensions(path):
    try:
        with Image.open(path) as img:
            width, height = img.size
            img.verify()
    except Exception as exc:
        raise UploadValidationError("invalid image file") from exc
    if width <= 0 or height <= 0 or width * height > MAX_UPLOAD_IMAGE_PIXELS:
        raise UploadValidationError(
            "image dimensions too large",
            width=width,
            height=height,
            max_pixels=MAX_UPLOAD_IMAGE_PIXELS,
        )


def validate_pdf_page_count(path):
    from pdf2image import pdfinfo_from_path

    try:
        info = pdfinfo_from_path(path, timeout=MEDIA_PROBE_TIMEOUT_SECONDS)
        page_count = int(info.get("Pages", 0) or 0)
    except Exception as exc:
        raise UploadValidationError("invalid pdf file") from exc
    if page_count <= 0:
        raise UploadValidationError("invalid pdf file")
    if page_count > MAX_UPLOAD_PDF_PAGES:
        raise UploadValidationError(
            "pdf page count too large",
            pages=page_count,
            max_pages=MAX_UPLOAD_PDF_PAGES,
        )
    return page_count


def get_video_duration_seconds(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
            capture_output=True,
            text=True,
            check=True,
            timeout=MEDIA_PROBE_TIMEOUT_SECONDS,
        )
        info = json.loads(result.stdout or "{}")
        return float(info.get("format", {}).get("duration", 0) or 0)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    except Exception as exc:
        raise UploadValidationError("invalid video file") from exc


def validate_video_duration(path):
    duration = get_video_duration_seconds(path)
    if duration is None:
        return
    if duration <= 0:
        raise UploadValidationError("invalid video file")
    if duration > MAX_UPLOAD_VIDEO_SECONDS:
        raise UploadValidationError(
            "video duration too long",
            duration_seconds=round(duration, 3),
            max_seconds=MAX_UPLOAD_VIDEO_SECONDS,
        )


def save_pdf_upload(file, filename, planned_filenames, username):
    from pdf2image import convert_from_path

    dest = os.path.join(UPLOAD_FOLDER, filename)
    file.save(dest)
    try:
        validate_pdf_page_count(dest)
        images = convert_from_path(dest, timeout=MEDIA_CONVERT_TIMEOUT_SECONDS)
        stem = os.path.splitext(filename)[0]
        for i, img in enumerate(images):
            width, height = img.size
            if width <= 0 or height <= 0 or width * height > MAX_UPLOAD_IMAGE_PIXELS:
                raise UploadValidationError(
                    "pdf page dimensions too large",
                    page=i + 1,
                    width=width,
                    height=height,
                    max_pixels=MAX_UPLOAD_IMAGE_PIXELS,
                )
            page_filename = f"{stem}_page_{i+1}.jpg"
            img_path = os.path.join(UPLOAD_FOLDER, page_filename)
            img.save(img_path, "JPEG", quality=95)
            generate_standard_renditions(page_filename)
            planned_filenames.add(page_filename)
        log_activity(username, "upload", filename=filename, details="pdf→jpg")
    finally:
        if os.path.exists(dest):
            os.remove(dest)


def _video_resolution_warnings(filename):
    width, height = get_video_dimensions(filename)
    if width <= 0 or height <= 0:
        return []
    longest_edge = max(width, height)
    shortest_edge = min(width, height)
    if longest_edge < 1920 or shortest_edge < 1080:
        return [_t("upload_video_too_small_for_hd", filename=filename, width=width, height=height)]
    if longest_edge < 3840 or shortest_edge < 2160:
        return [_t("upload_video_too_small_for_4k", filename=filename, width=width, height=height)]
    return []


def save_video_upload(file, filename, queued_video_files, upload_warnings, username):
    dest = os.path.join(UPLOAD_FOLDER, filename)
    file.save(dest)
    validate_video_duration(dest)
    upload_warnings.extend(_video_resolution_warnings(filename))
    cfg = load_config()
    disabled = cfg.setdefault("disabled", [])
    if filename not in disabled:
        disabled.append(filename)
    save_config(cfg)
    enqueue_compress_job(filename)
    queued_video_files.append(filename)
    log_activity(username, "upload", filename=filename, details="queued for nightly encoding")


def save_image_upload(file, filename, username):
    dest = os.path.join(UPLOAD_FOLDER, filename)
    file.save(dest)
    try:
        validate_image_dimensions(dest)
    except UploadValidationError:
        os.remove(dest)
        raise
    if not is_valid_uploaded_image(dest):
        os.remove(dest)
        raise UploadValidationError("invalid image file")
    generate_standard_renditions(filename)
    log_activity(username, "upload", filename=filename)


def _json_error(payload, status_code):
    return jsonify(payload), status_code


def handle_media_upload(files, form_data, username):
    if not files:
        _flash("flash_no_file", "error")
        return redirect(url_for("admin.admin_page"))

    conflict_strategy = normalize_conflict_strategy(form_data.get("conflict_strategy"))
    rename_map = load_rename_map(form_data)
    videos_enabled = are_videos_enabled()
    if not conflict_strategy:
        conflicts = collect_upload_name_conflicts(files)
        if conflicts:
            return _json_error({"error": "name conflict", "conflicts": conflicts}, 409)

    total_size = sum(get_uploaded_file_size(file) for file in files if file and file.filename)
    if total_size > MAX_BATCH_UPLOAD_SIZE:
        return _json_error({"error": "batch too large"}, 400)

    queued_video_files = []
    upload_warnings = []
    planned_filenames = set()
    for file_index, file in enumerate(files):
        if not file or file.filename == "":
            continue
        if get_uploaded_file_size(file) > MAX_FILE_UPLOAD_SIZE:
            return _json_error({"error": "file too large"}, 400)
        filename = clean_filename(file.filename)
        if not filename:
            continue
        ext = os.path.splitext(filename)[1].lower()
        if not has_supported_extension(filename, videos_enabled=videos_enabled):
            return _json_error({"error": "unsupported file type"}, 400)

        path_exists = os.path.exists(os.path.join(UPLOAD_FOLDER, filename))
        duplicate_in_batch = filename in planned_filenames
        needs_rename = path_exists or duplicate_in_batch

        if conflict_strategy == "rename_custom" and needs_rename:
            renamed_filename, rename_error = resolve_custom_rename(file_index, filename, rename_map)
            if rename_error:
                return _json_error({"error": rename_error, "filename": filename}, 400)
            if (
                renamed_filename in planned_filenames
                or os.path.exists(os.path.join(UPLOAD_FOLDER, renamed_filename))
            ):
                return _json_error({
                    "error": "name conflict",
                    "conflicts": [{
                        "upload_index": file_index,
                        "filename": filename,
                    }],
                    "message": f"The chosen name already exists: {rename_map.get(str(file_index), filename)}",
                }, 409)
            filename = renamed_filename
        elif conflict_strategy == "overwrite" and path_exists:
            prepare_overwrite_target(filename)
        elif needs_rename:
            return _json_error({
                "error": "name conflict",
                "conflicts": [{
                    "upload_index": file_index,
                    "filename": filename,
                }],
            }, 409)

        planned_filenames.add(filename)

        try:
            if ext == ".pdf":
                save_pdf_upload(file, filename, planned_filenames, username)
            elif ext in VIDEO_EXTS:
                save_video_upload(file, filename, queued_video_files, upload_warnings, username)
            else:
                save_image_upload(file, filename, username)
        except UploadValidationError as exc:
            prepare_overwrite_target(filename)
            return _json_error(exc.payload, exc.status_code)

    redirect_url = "/admin/media"
    if queued_video_files:
        redirect_url = "/admin/queue"
    bump_media_revision()
    return jsonify({
        "ok": True,
        "queued_files": queued_video_files,
        "redirect": redirect_url,
        "warnings": upload_warnings,
    })
