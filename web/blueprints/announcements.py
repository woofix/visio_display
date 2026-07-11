# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for

from blueprints.guards import admin_guard, feature_guard
from constants import UPLOAD_FOLDER
from services.announcement_svc import (
    _safe_image_url,
    create_announcement,
    fetch_thumbnail_bytes,
    image_media_choices,
    pexels_search,
)
from services.config_svc import get_default_screen_name, get_screen_keys, load_config, normalize_screen_key
from services.icon_svc import scan_svg_icons
from services.i18n import _flash, _t
from services.media_svc import build_media_preview_map, get_logo_path, get_media_url
from services.qr_svc import image_to_data_url, render_qr_image, save_qr_media
from services.users_svc import has_permission, has_screen_access, is_superadmin, load_users


bp = Blueprint("announcements", __name__)


def _has_announcements_permission():
    return has_permission("announcements") or has_permission("upload")


def _screen_choices(cfg):
    default_key = normalize_screen_key("", cfg)
    default_label = get_default_screen_name(cfg) or _t("announcements_default_screen_label")
    screens = []
    seen = set()
    for screen in get_screen_keys(cfg):
        if screen in seen or not has_screen_access(screen):
            continue
        seen.add(screen)
        screens.append({
            "value": "__default__" if screen == default_key else screen,
            "label": default_label if screen == default_key else screen,
        })
    return screens


@bp.route("/admin/announcements")
def admin_announcements_page():
    redir = admin_guard()
    if redir:
        return redir
    redir = feature_guard("announcements")
    if redir:
        return redir
    if not _has_announcements_permission():
        _flash("flash_no_perm_announcements", "error")
        return redirect(url_for("admin.admin_page"))

    cfg = load_config()
    media_choices = image_media_choices()
    media_preview_map = build_media_preview_map(
        media_choices,
        context="campaign",
        generate_missing=False,
        placeholder_url="",
    )
    media_original_map = {
        filename: get_media_url(filename, context="preview", allow_original=True, generate_missing=False)
        for filename in media_choices
    }
    users = load_users()
    return render_template(
        "admin_announcements.html",
        users=list(users.keys()),
        current_user=session.get("user"),
        current_user_is_superadmin=is_superadmin(),
        logo_path=get_logo_path(),
        media_choices=media_choices,
        media_preview_map=media_preview_map,
        media_original_map=media_original_map,
        screens=_screen_choices(cfg),
        can_upload=_has_announcements_permission(),
    )


@bp.route("/admin/announcements/search-backgrounds")
def search_backgrounds():
    redir = admin_guard()
    if redir:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    redir = feature_guard("announcements")
    if redir:
        return jsonify({"ok": False, "error": "feature disabled"}), 403
    if not _has_announcements_permission():
        return jsonify({"ok": False, "error": "permission denied"}), 403
    query = request.args.get("q", "").strip()
    try:
        return jsonify({"ok": True, "results": pexels_search(query)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc) or "search failed"}), 502


@bp.route("/admin/announcements/background-thumb")
def background_thumb():
    redir = admin_guard()
    if redir:
        return "", 401
    redir = feature_guard("announcements")
    if redir:
        return "", 403
    if not _has_announcements_permission():
        return "", 403
    url = request.args.get("url", "")
    fallback_url = request.args.get("fallback", "")
    if not _safe_image_url(url):
        return "", 400
    try:
        return Response(fetch_thumbnail_bytes(url), mimetype="image/jpeg")
    except Exception:
        if fallback_url and _safe_image_url(fallback_url) and fallback_url != url:
            try:
                return Response(fetch_thumbnail_bytes(fallback_url), mimetype="image/jpeg")
            except Exception:
                pass
        return "", 502


@bp.route("/admin/announcements/icons")
def announcement_icons():
    redir = admin_guard()
    if redir:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    redir = feature_guard("announcements")
    if redir:
        return jsonify({"ok": False, "error": "feature disabled"}), 403
    if not _has_announcements_permission():
        return jsonify({"ok": False, "error": "permission denied"}), 403
    return jsonify({
        "ok": True,
        **scan_svg_icons(
            category=request.args.get("category"),
            query=request.args.get("q", ""),
            limit=request.args.get("limit", 60),
            offset=request.args.get("offset", 0),
        ),
    })


@bp.route("/admin/announcements/qr-code", methods=["POST"])
def announcement_qr_code():
    redir = admin_guard()
    if redir:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    redir = feature_guard("announcements")
    if redir:
        return jsonify({"ok": False, "error": "feature disabled"}), 403
    if not _has_announcements_permission():
        return jsonify({"ok": False, "error": "permission denied"}), 403

    data = request.get_json(silent=True) or {}
    logo_path = None
    logo_filename = str(data.get("logo_filename") or "").strip()
    if logo_filename:
        allowed_logos = set(image_media_choices())
        if logo_filename not in allowed_logos:
            return jsonify({"ok": False, "error": _t("qr_error_logo_invalid")}), 400
        logo_path = os.path.join(UPLOAD_FOLDER, logo_filename)

    try:
        image, payload = render_qr_image(data, logo_path=logo_path)
        result = {"ok": True, "payload": payload, "data_url": image_to_data_url(image)}
        if data.get("save"):
            result.update(save_qr_media(image, data, username=session.get("user")))
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc) or _t("qr_error_generation_failed")}), 400


@bp.route("/admin/announcements/create", methods=["POST"])
def create_announcement_route():
    redir = admin_guard()
    if redir:
        return redir
    redir = feature_guard("announcements")
    if redir:
        return redir
    if not _has_announcements_permission():
        _flash("flash_no_perm_announcements", "error")
        return redirect(url_for("announcements.admin_announcements_page"))

    try:
        filename = create_announcement(
            request.form,
            uploaded_file=request.files.get("background_upload"),
            layer_uploads=request.files.getlist("layer_uploads"),
            username=session.get("user"),
        )
    except Exception as exc:
        _flash("flash_announcement_failed", "error", error=str(exc) or _t("generic_unknown_error"))
        return redirect(url_for("announcements.admin_announcements_page"))

    _flash("flash_announcement_created", "success", filename=filename)
    return redirect(url_for("media.admin_media"))
