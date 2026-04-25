# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

from datetime import date, datetime
from uuid import uuid4

from services.media_svc import (
    get_all_media,
    get_media_groups,
    is_group_active_on_screen,
    normalize_group_name,
)


def normalize_campaign_name(value):
    return " ".join(str(value or "").split())[:80]


def normalize_campaign_list(raw_values, *, normalizer=None, max_items=200):
    if isinstance(raw_values, str):
        raw_values = raw_values.split(",")
    if not isinstance(raw_values, list):
        return []

    values = []
    seen = set()
    for item in raw_values:
        value = item
        if normalizer is not None:
            value = normalizer(item)
        else:
            value = str(item or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        values.append(value)
        seen.add(key)
        if len(values) >= max_items:
            break
    return values


def normalize_campaign(raw_campaign, *, valid_screens=None, valid_media=None):
    raw_campaign = raw_campaign if isinstance(raw_campaign, dict) else {}
    valid_screens = set(valid_screens or [])
    valid_media = set(valid_media or [])

    campaign_id = str(raw_campaign.get("id") or "").strip() or uuid4().hex
    name = normalize_campaign_name(raw_campaign.get("name", ""))

    start_date = str(raw_campaign.get("start_date", "") or "").strip()
    end_date = str(raw_campaign.get("end_date", "") or "").strip()
    for key, value in (("start_date", start_date), ("end_date", end_date)):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                if key == "start_date":
                    start_date = ""
                else:
                    end_date = ""

    try:
        priority = int(raw_campaign.get("priority", 100))
    except (TypeError, ValueError):
        priority = 100
    priority = max(1, min(priority, 999))

    screens = normalize_campaign_list(raw_campaign.get("screens", []))
    if valid_screens:
        screens = [screen for screen in screens if screen in valid_screens]

    groups = normalize_campaign_list(
        raw_campaign.get("groups", []),
        normalizer=normalize_group_name,
        max_items=100,
    )

    media = normalize_campaign_list(raw_campaign.get("media", []))
    if valid_media:
        media = [filename for filename in media if filename in valid_media]

    return {
        "id": campaign_id,
        "name": name or "Campagne sans nom",
        "start_date": start_date,
        "end_date": end_date,
        "priority": priority,
        "enabled": bool(raw_campaign.get("enabled", False)),
        "archived": bool(raw_campaign.get("archived", False)),
        "screens": screens,
        "groups": groups,
        "media": media,
        "created_by": str(raw_campaign.get("created_by") or "").strip(),
        "created_at": str(raw_campaign.get("created_at") or "").strip() or datetime.now().isoformat(timespec="seconds"),
        "updated_at": str(raw_campaign.get("updated_at") or "").strip() or datetime.now().isoformat(timespec="seconds"),
    }


def get_campaigns(cfg):
    valid_screens = list((cfg or {}).get("screens", {}).keys())
    valid_media = get_all_media()
    campaigns = [
        normalize_campaign(item, valid_screens=valid_screens, valid_media=valid_media)
        for item in (cfg or {}).get("campaigns", [])
        if isinstance(item, dict)
    ]
    campaigns.sort(key=lambda item: (item.get("archived", False), -item.get("priority", 0), item.get("name", "").casefold()))
    return campaigns


def save_campaigns_to_config(cfg, campaigns):
    valid_screens = list((cfg or {}).get("screens", {}).keys())
    valid_media = get_all_media()
    cfg["campaigns"] = [
        normalize_campaign(item, valid_screens=valid_screens, valid_media=valid_media)
        for item in campaigns
        if isinstance(item, dict)
    ]


def campaign_matches_screen(campaign, screen):
    screens = campaign.get("screens", [])
    return not screens or str(screen or "").strip().lower() in screens


def campaign_is_active(campaign, now=None):
    if not campaign.get("enabled") or campaign.get("archived"):
        return False

    today = (now or datetime.now()).date()
    start_date = campaign.get("start_date")
    end_date = campaign.get("end_date")

    if start_date:
        try:
            if today < date.fromisoformat(start_date):
                return False
        except ValueError:
            return False
    if end_date:
        try:
            if today > date.fromisoformat(end_date):
                return False
        except ValueError:
            return False
    return True


def campaign_target_media(campaign, cfg, *, screen="", available_files=None):
    if screen and not campaign_matches_screen(campaign, screen):
        return set()

    available = set(available_files or get_all_media())
    selected = {filename for filename in campaign.get("media", []) if filename in available}
    group_targets = set(campaign.get("groups", []))
    if not group_targets:
        return selected

    for filename in available:
        media_groups = get_media_groups(filename, cfg)
        for group_name in media_groups:
            if group_name not in group_targets:
                continue
            if screen and not is_group_active_on_screen(group_name, cfg, screen):
                continue
            selected.add(filename)
            break
    return selected


def order_campaign_media(filenames, ordered_files):
    selected = set(filenames)
    ordered = [filename for filename in ordered_files if filename in selected]
    leftovers = sorted(selected.difference(ordered), key=str.casefold)
    return ordered + leftovers


def resolve_campaign_override(cfg, screen=""):
    campaigns = [
        campaign for campaign in get_campaigns(cfg)
        if campaign_is_active(campaign) and campaign_matches_screen(campaign, screen)
    ]
    if not campaigns:
        return None

    top_priority = max(campaign.get("priority", 0) for campaign in campaigns)
    selected_campaigns = [campaign for campaign in campaigns if campaign.get("priority", 0) == top_priority]
    ordered_media = get_all_media()
    targeted = set()
    for campaign in selected_campaigns:
        targeted.update(campaign_target_media(campaign, cfg, screen=screen, available_files=ordered_media))

    if not targeted:
        return None

    return {
        "priority": top_priority,
        "campaigns": selected_campaigns,
        "files": order_campaign_media(targeted, ordered_media),
    }


def campaign_target_counts(campaign, cfg):
    media_count = len(campaign_target_media(campaign, cfg))
    return {
        "screens": len(campaign.get("screens", [])),
        "groups": len(campaign.get("groups", [])),
        "media": len(campaign.get("media", [])),
        "resolved_media": media_count,
    }


def serialize_campaign_for_view(campaign, cfg):
    counts = campaign_target_counts(campaign, cfg)
    return {
        **campaign,
        "is_active": campaign_is_active(campaign),
        "target_counts": counts,
    }


def campaign_allowed_for_user(campaign, allowed_screens, *, is_superadmin=False):
    if is_superadmin:
        return True
    screens = campaign.get("screens", [])
    if not screens:
        return False
    return bool(set(screens) & set(allowed_screens))


def cleanup_campaigns_for_deleted_media(campaigns, filename):
    updated = []
    for campaign in campaigns:
        clone = dict(campaign)
        clone["media"] = [item for item in campaign.get("media", []) if item != filename]
        clone["updated_at"] = datetime.now().isoformat(timespec="seconds")
        updated.append(clone)
    return updated


def cleanup_campaigns_for_deleted_screen(campaigns, screen_name):
    updated = []
    for campaign in campaigns:
        screens = campaign.get("screens", [])
        if screen_name not in screens:
            updated.append(campaign)
            continue
        remaining = [screen for screen in screens if screen != screen_name]
        clone = dict(campaign)
        clone["screens"] = remaining
        if not remaining:
            clone["enabled"] = False
            clone["archived"] = True
        clone["updated_at"] = datetime.now().isoformat(timespec="seconds")
        updated.append(clone)
    return updated
