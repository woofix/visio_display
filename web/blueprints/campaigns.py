# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for

from services.activity_svc import log_activity
from services.campaign_svc import (
    campaign_allowed_for_user,
    get_campaigns,
    normalize_campaign,
    save_campaigns_to_config,
    serialize_campaign_for_view,
)
from services.config_svc import get_screen_keys, load_config, save_config, get_default_screen_name, normalize_screen_key
from services.i18n import _flash
from services.media_svc import (
    build_media_preview_map,
    get_all_media,
    get_file_info,
    get_logo_path,
    get_media_url,
    normalize_group_name,
)
from services.users_svc import has_permission, has_screen_access, is_superadmin, load_users
from blueprints.guards import admin_guard, feature_guard

bp = Blueprint("campaigns", __name__)


def _allowed_screens(cfg):
    return [screen for screen in get_screen_keys(cfg) if has_screen_access(screen)]


def _screen_choices(cfg):
    choices = []
    if has_screen_access(''):
        choices.append(("__default__", ""))
    choices.extend((screen, screen) for screen in _allowed_screens(cfg))
    return choices


def _campaign_redirect(campaign_id=None):
    if campaign_id:
        return redirect(url_for("campaigns.admin_campaigns_page", campaign=campaign_id))
    return redirect(url_for("campaigns.admin_campaigns_page"))


def _get_visible_campaigns(cfg):
    allowed_screens = _allowed_screens(cfg)
    visible = []
    for campaign in get_campaigns(cfg):
        if campaign_allowed_for_user(campaign, allowed_screens, is_superadmin=is_superadmin()):
            visible.append(serialize_campaign_for_view(campaign, cfg))
    return visible


def _build_media_items():
    files = get_all_media()
    preview_map = build_media_preview_map(files, context='campaign')
    items = []
    for filename in files:
        info = get_file_info(filename, include_dimensions=False)
        items.append(
            {
                "filename": filename,
                "type": info.get("type", "unknown"),
                "size": info.get("size", "--"),
                "dims": info.get("dims", "--"),
                "preview_url": preview_map.get(filename),
                "playback_url": get_media_url(
                    filename,
                    context='preview',
                    allow_original=True,
                    generate_missing=False,
                ),
            }
        )
    return items


def _parse_campaign_form(cfg, raw_data):
    name = str(raw_data.get("name", "")).strip()
    if not name:
        return None, "flash_campaign_name_required"

    try:
        priority = int(raw_data.get("priority", 100))
    except (TypeError, ValueError):
        return None, "flash_campaign_priority_invalid"

    start_date = str(raw_data.get("start_date", "")).strip()
    end_date = str(raw_data.get("end_date", "")).strip()
    if start_date and end_date and start_date > end_date:
        return None, "flash_campaign_dates_invalid"

    groups = [
        normalize_group_name(item)
        for item in str(raw_data.get("groups", "")).split(",")
    ]
    groups = [item for item in groups if item]
    media = [item for item in raw_data.getlist("media") if item]
    raw_screens = raw_data.getlist("screens")
    screens = [normalize_screen_key("" if item == "__default__" else item, cfg) for item in raw_screens]

    if not groups and not media:
        return None, "flash_campaign_targets_required"

    allowed_screens = set(_allowed_screens(cfg))
    if not is_superadmin():
        if not screens:
            return None, "flash_campaign_screen_required"
        if any(screen not in allowed_screens for screen in screens):
            return None, "flash_no_screen_access"

    campaign = normalize_campaign(
        {
            "id": raw_data.get("campaign_id"),
            "name": name,
            "start_date": start_date,
            "end_date": end_date,
            "priority": priority,
            "enabled": str(raw_data.get("enabled", "")).lower() in {"1", "true", "on", "yes"},
            "archived": str(raw_data.get("archived", "")).lower() in {"1", "true", "on", "yes"},
            "screens": screens,
            "groups": groups,
            "media": media,
            "created_at": raw_data.get("created_at"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        valid_screens=get_screen_keys(cfg),
        valid_media=get_all_media(),
    )
    return campaign, None


@bp.route("/admin/campaigns")
def admin_campaigns_page():
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir

    cfg = load_config()
    users = load_users()
    group_choices = sorted(
        {
            group
            for groups in cfg.get("groups", {}).values()
            if isinstance(groups, list)
            for group in groups
            if normalize_group_name(group)
        },
        key=str.casefold,
    )
    media_items = _build_media_items()

    return render_template(
        "admin_campaigns.html",
        campaigns=_get_visible_campaigns(cfg),
        media_choices=[item["filename"] for item in media_items],
        media_items=media_items,
        media_map={item["filename"]: item for item in media_items},
        group_choices=group_choices,
        available_screen_choices=_screen_choices(cfg),
        current_campaign=request.args.get("campaign", "").strip(),
        users=list(users.keys()),
        current_user=session.get("user"),
        default_screen_name=get_default_screen_name(cfg) or "",
        logo_path=get_logo_path(),
        current_user_is_superadmin=is_superadmin(),
        can_manage_campaigns=has_permission("schedule") or has_permission("toggle"),
    )


@bp.route("/admin/campaigns/create", methods=["POST"])
def create_campaign():
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir
    if not (has_permission("schedule") or has_permission("toggle")):
        _flash("flash_campaign_permission_denied", "error")
        return _campaign_redirect()

    cfg = load_config()
    campaign, error_key = _parse_campaign_form(cfg, request.form)
    if error_key:
        _flash(error_key, "error")
        return _campaign_redirect()

    campaign["created_by"] = session.get("user", "")
    campaigns = get_campaigns(cfg)
    campaigns.insert(0, campaign)
    save_campaigns_to_config(cfg, campaigns)
    save_config(cfg)
    log_activity(session.get("user"), "campaign", details=f'created:{campaign["name"]}')
    _flash("flash_campaign_created", "success", name=campaign["name"])
    return _campaign_redirect(campaign["id"])


@bp.route("/admin/campaigns/<campaign_id>/update", methods=["POST"])
def update_campaign(campaign_id):
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir
    if not (has_permission("schedule") or has_permission("toggle")):
        _flash("flash_campaign_permission_denied", "error")
        return _campaign_redirect()

    cfg = load_config()
    campaigns = get_campaigns(cfg)
    current = next((item for item in campaigns if item["id"] == campaign_id), None)
    if current is None:
        _flash("flash_campaign_not_found", "error")
        return _campaign_redirect()

    if not campaign_allowed_for_user(current, _allowed_screens(cfg), is_superadmin=is_superadmin()):
        _flash("flash_no_screen_access", "error")
        return _campaign_redirect()

    current_user = session.get("user")
    owner = current.get("created_by", "")
    if not is_superadmin() and owner and owner != current_user:
        _flash("flash_campaign_edit_denied", "error")
        return _campaign_redirect(campaign_id)

    payload = request.form.copy()
    payload["campaign_id"] = campaign_id
    payload["created_at"] = current.get("created_at", "")
    campaign, error_key = _parse_campaign_form(cfg, payload)
    if error_key:
        _flash(error_key, "error")
        return _campaign_redirect(campaign_id)

    campaign["created_by"] = current.get("created_by", "")
    updated = [campaign if item["id"] == campaign_id else item for item in campaigns]
    save_campaigns_to_config(cfg, updated)
    save_config(cfg)
    log_activity(session.get("user"), "campaign", details=f'updated:{campaign["name"]}')
    _flash("flash_campaign_updated", "success", name=campaign["name"])
    return _campaign_redirect(campaign_id)


@bp.route("/admin/campaigns/<campaign_id>/toggle", methods=["POST"])
def toggle_campaign(campaign_id):
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir
    if not (has_permission("schedule") or has_permission("toggle")):
        _flash("flash_campaign_permission_denied", "error")
        return _campaign_redirect()

    cfg = load_config()
    campaigns = get_campaigns(cfg)
    for campaign in campaigns:
        if campaign["id"] != campaign_id:
            continue
        if not campaign_allowed_for_user(campaign, _allowed_screens(cfg), is_superadmin=is_superadmin()):
            _flash("flash_no_screen_access", "error")
            return _campaign_redirect()
        _owner = campaign.get("created_by", "")
        if not is_superadmin() and _owner and _owner != session.get("user"):
            _flash("flash_campaign_edit_denied", "error")
            return _campaign_redirect(campaign_id)
        if campaign.get("archived"):
            _flash("flash_campaign_archived_toggle_blocked", "error")
            return _campaign_redirect(campaign_id)
        campaign["enabled"] = not campaign.get("enabled", False)
        campaign["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_campaigns_to_config(cfg, campaigns)
        save_config(cfg)
        log_activity(session.get("user"), "campaign", details=f'toggled:{campaign["name"]}:{campaign["enabled"]}')
        _flash("flash_campaign_toggled", "success", name=campaign["name"])
        return _campaign_redirect(campaign_id)

    _flash("flash_campaign_not_found", "error")
    return _campaign_redirect()


@bp.route("/admin/campaigns/<campaign_id>/duplicate", methods=["POST"])
def duplicate_campaign(campaign_id):
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir
    if not (has_permission("schedule") or has_permission("toggle")):
        _flash("flash_campaign_permission_denied", "error")
        return _campaign_redirect()

    cfg = load_config()
    campaigns = get_campaigns(cfg)
    source = next((item for item in campaigns if item["id"] == campaign_id), None)
    if source is None:
        _flash("flash_campaign_not_found", "error")
        return _campaign_redirect()
    if not campaign_allowed_for_user(source, _allowed_screens(cfg), is_superadmin=is_superadmin()):
        _flash("flash_no_screen_access", "error")
        return _campaign_redirect()

    duplicate = normalize_campaign(
        {
            **source,
            "id": "",
            "name": f'{source["name"]} (copie)',
            "enabled": False,
            "archived": False,
            "created_by": session.get("user", ""),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        valid_screens=get_screen_keys(cfg),
        valid_media=get_all_media(),
    )
    campaigns.insert(0, duplicate)
    save_campaigns_to_config(cfg, campaigns)
    save_config(cfg)
    log_activity(session.get("user"), "campaign", details=f'duplicated:{source["name"]}')
    _flash("flash_campaign_duplicated", "success", name=duplicate["name"])
    return _campaign_redirect(duplicate["id"])


@bp.route("/admin/campaigns/<campaign_id>/delete", methods=["POST"])
def delete_campaign(campaign_id):
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir
    if not (has_permission("schedule") or has_permission("toggle")):
        _flash("flash_campaign_permission_denied", "error")
        return _campaign_redirect()

    cfg = load_config()
    campaigns = get_campaigns(cfg)
    target = next((item for item in campaigns if item["id"] == campaign_id), None)
    if target is None:
        _flash("flash_campaign_not_found", "error")
        return _campaign_redirect()

    current_user = session.get("user")
    owner = target.get("created_by", "")
    if not is_superadmin() and owner and owner != current_user:
        _flash("flash_campaign_delete_denied", "error")
        return _campaign_redirect()

    updated = [item for item in campaigns if item["id"] != campaign_id]
    save_campaigns_to_config(cfg, updated)
    save_config(cfg)
    log_activity(current_user, "campaign", details=f'deleted:{target["name"]}')
    _flash("flash_campaign_deleted", "success", name=target["name"])
    return _campaign_redirect()


@bp.route("/admin/campaigns/<campaign_id>/archive", methods=["POST"])
def archive_campaign(campaign_id):
    redir = admin_guard() or feature_guard('campaigns')
    if redir:
        return redir
    if not (has_permission("schedule") or has_permission("toggle")):
        _flash("flash_campaign_permission_denied", "error")
        return _campaign_redirect()

    cfg = load_config()
    campaigns = get_campaigns(cfg)
    for campaign in campaigns:
        if campaign["id"] != campaign_id:
            continue
        if not campaign_allowed_for_user(campaign, _allowed_screens(cfg), is_superadmin=is_superadmin()):
            _flash("flash_no_screen_access", "error")
            return _campaign_redirect()
        _owner = campaign.get("created_by", "")
        if not is_superadmin() and _owner and _owner != session.get("user"):
            _flash("flash_campaign_edit_denied", "error")
            return _campaign_redirect(campaign_id)
        campaign["archived"] = not campaign.get("archived", False)
        if campaign["archived"]:
            campaign["enabled"] = False
        campaign["updated_at"] = datetime.now().isoformat(timespec="seconds")
        save_campaigns_to_config(cfg, campaigns)
        save_config(cfg)
        log_activity(session.get("user"), "campaign", details=f'archived:{campaign["name"]}:{campaign["archived"]}')
        _flash("flash_campaign_archived", "success", name=campaign["name"])
        return _campaign_redirect(campaign_id)

    _flash("flash_campaign_not_found", "error")
    return _campaign_redirect()
