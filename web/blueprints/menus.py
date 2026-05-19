# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, jsonify, redirect, render_template, request, send_file, session, url_for

from blueprints.guards import admin_guard, feature_guard
from services.config_svc import get_default_screen_name, load_config
from services.i18n import _flash, _t
from services.image_suggestions_svc import cached_image_path
from services.menu_svc import (
    build_menu_schedule,
    enqueue_menu_from_text,
    create_weekly_menus_from_form,
    suggest_menu_sections,
)
from services.users_svc import has_permission, has_screen_access, is_superadmin, load_users
from services.media_svc import get_logo_path


bp = Blueprint("menus", __name__)


def _has_menu_permission():
    return has_permission("menus")


def _screen_choices(cfg):
    screens = []
    if has_screen_access(""):
        screens.append({"value": "__default__", "label": get_default_screen_name(cfg) or _t("announcements_default_screen_label")})
    screens.extend({"value": screen, "label": screen} for screen in cfg.get("screens", {}) if has_screen_access(screen))
    return screens


@bp.route("/admin/menus")
def admin_menus_page():
    redir = admin_guard()
    if redir:
        return redir
    redir = feature_guard("menus")
    if redir:
        return redir
    if not _has_menu_permission():
        _flash("flash_no_perm_menus", "error")
        return redirect(url_for("admin.admin_page"))
    cfg = load_config()
    users = load_users()
    return render_template(
        "admin_menus.html",
        users=list(users.keys()),
        current_user=session.get("user"),
        current_user_is_superadmin=is_superadmin(),
        logo_path=get_logo_path(),
        screens=_screen_choices(cfg),
    )


@bp.route("/admin/menus/suggest", methods=["POST"])
def suggest_menu():
    redir = admin_guard()
    if redir:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    redir = feature_guard("menus")
    if redir:
        return jsonify({"ok": False, "error": "feature disabled"}), 403
    if not _has_menu_permission():
        return jsonify({"ok": False, "error": "permission denied"}), 403
    data = request.get_json(silent=True) or {}
    suggestions = suggest_menu_sections(data.get("sections"), fallback_text=data.get("text", ""), cache_external=True)
    return jsonify({"ok": True, **suggestions})


@bp.route("/admin/menus/suggestion-cache/<path:filename>")
def menu_suggestion_cache(filename):
    redir = admin_guard()
    if redir:
        return "", 401
    redir = feature_guard("menus")
    if redir:
        return "", 403
    if not _has_menu_permission():
        return "", 403
    path = cached_image_path(filename)
    if not path:
        return "", 404
    return send_file(path)


@bp.route("/admin/menus/create", methods=["POST"])
def create_menu():
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    redir = admin_guard()
    if redir:
        if wants_json:
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        return redir
    redir = feature_guard("menus")
    if redir:
        if wants_json:
            return jsonify({"ok": False, "error": "feature disabled"}), 403
        return redir
    if not _has_menu_permission():
        if wants_json:
            return jsonify({"ok": False, "error": "permission denied"}), 403
        _flash("flash_no_perm_menus", "error")
        return redirect(url_for("menus.admin_menus_page"))
    try:
        schedule = build_menu_schedule(request.form)
        weekly_mode = request.form.get("menu_mode") == "week"
        if weekly_mode:
            filenames = create_weekly_menus_from_form(
                request.form.get("title"),
                request.form,
                duration=request.form.get("duration"),
                schedule=schedule,
                screens=request.form.getlist("screens"),
                username=session.get("user"),
                image_choices=request.form.get("image_choices"),
                queue_generation=True,
            )
            filename = ", ".join(filenames)
        else:
            if schedule.get("date_start"):
                schedule["date_end"] = schedule["date_start"]
            filename = enqueue_menu_from_text(
                request.form.get("title"),
                request.form.get("menu_text"),
                sections={
                    "starter": request.form.get("starter_text"),
                    "main": request.form.get("main_text"),
                    "dessert": request.form.get("dessert_text"),
                },
                duration=request.form.get("duration"),
                schedule=schedule,
                screens=request.form.getlist("screens"),
                username=session.get("user"),
                image_choices=request.form.get("image_choices"),
            )
    except Exception as exc:
        error = str(exc) or _t("generic_unknown_error")
        if wants_json:
            return jsonify({"ok": False, "error": error}), 400
        _flash("flash_announcement_failed", "error", error=str(exc) or _t("generic_unknown_error"))
        return redirect(url_for("menus.admin_menus_page"))
    if wants_json:
        return jsonify({
            "ok": True,
            "filename": filename,
            "message": _t("flash_menu_queued", filename=filename),
            "redirect": url_for("queue.admin_queue_view"),
        })
    _flash("flash_menu_queued", "success", filename=filename)
    return redirect(url_for("queue.admin_queue_view"))
