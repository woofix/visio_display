# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import json
import math
import subprocess
import tempfile
import unicodedata
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont, ImageOps

from constants import UPLOAD_FOLDER
from services.activity_svc import log_activity
from services.config_svc import load_config, save_config
from services.image_suggestions_svc import cache_external_image, suggest_images
from services.keyword_recognition_svc import extract_keywords
from services.media_svc import (
    clean_filename,
    cleanup_orphan_group_metadata,
    delete_image_variants,
    delete_media_thumbnail,
    delete_video_variants,
    ensure_unique_filename,
    generate_standard_renditions,
)
from services.queue_svc import load_queue, save_queue
from services.queue_svc import enqueue_menu_generation_job
from services.schedule_svc import parse_iso_date, parse_time_to_minutes


MENU_SIZE = (1920, 1080)
MENU_VIDEO_DURATION_SECONDS = 15
MENU_SECTIONS = (
    ("starter", "Entrée"),
    ("main", "Plat"),
    ("dessert", "Dessert"),
)
SECTION_ACCENTS = (
    (255, 107, 107),
    (75, 123, 236),
    (32, 201, 151),
)
MENU_SCHEDULE_KEYS = ("date_start", "date_end", "time_start", "time_end")
WEEKDAY_SECTION_KEYS = tuple(key for key, _label in MENU_SECTIONS)
WEEKDAY_ALIASES = {
    "lundi": 0,
    "lun": 0,
    "monday": 0,
    "mon": 0,
    "mardi": 1,
    "mar": 1,
    "tuesday": 1,
    "tue": 1,
    "mercredi": 2,
    "mer": 2,
    "wednesday": 2,
    "wed": 2,
    "jeudi": 3,
    "jeu": 3,
    "thursday": 3,
    "thu": 3,
    "vendredi": 4,
    "ven": 4,
    "friday": 4,
    "fri": 4,
    "samedi": 5,
    "sam": 5,
    "saturday": 5,
    "sat": 5,
    "dimanche": 6,
    "dim": 6,
    "sunday": 6,
    "sun": 6,
}
WEEKDAY_TITLES = (
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche",
)


def parse_menu_lines(text):
    lines = []
    for raw_line in str(text or "").splitlines():
        line = " ".join(raw_line.strip(" -\t").split())
        if line:
            lines.append(line[:120])
    return lines[:10]


def parse_menu_sections(sections=None, fallback_text=None):
    parsed = []
    sections = sections if isinstance(sections, dict) else {}
    for key, label in MENU_SECTIONS:
        lines = parse_menu_lines(sections.get(key))
        if lines:
            parsed.append({"key": key, "label": label, "lines": lines[:4]})
    if not parsed and fallback_text:
        parsed.append({"key": "main", "label": "Plat", "lines": parse_menu_lines(fallback_text)})
    return parsed


def flatten_menu_sections(sections):
    items = []
    for section in sections:
        for line in section.get("lines", []):
            items.append({"section": section.get("key", "main"), "section_label": section.get("label", "Plat"), "text": line})
    return items


def _cache_external_suggestion(suggestion):
    if not suggestion or suggestion.get("source") == "local" or not suggestion.get("external_url"):
        return suggestion
    try:
        cached = cache_external_image(suggestion["external_url"])
    except Exception:
        return suggestion
    updated = dict(suggestion)
    updated.update({
        "source": "cache",
        "local_path": cached.get("local_path") or "",
        "local_url": cached.get("local_url") or "",
        "preview_url": cached.get("local_url") or suggestion.get("preview_url") or "",
    })
    return updated


def _safe_choice(choice):
    if not isinstance(choice, dict):
        return None
    source = str(choice.get("source") or "").strip()
    if source == "local" and choice.get("local_path"):
        return choice
    if choice.get("external_url"):
        return _cache_external_suggestion(choice)
    if choice.get("local_path"):
        return choice
    return None


def parse_menu_image_choices(raw_choices):
    if not raw_choices:
        return {}
    if isinstance(raw_choices, str):
        try:
            raw_choices = json.loads(raw_choices)
        except (TypeError, json.JSONDecodeError):
            return {}
    if not isinstance(raw_choices, dict):
        return {}
    choices = {}
    for key, value in raw_choices.items():
        line = " ".join(str(key or "").split())[:120]
        choice = _safe_choice(value)
        if line and choice:
            choices[line] = choice
    return choices


def build_menu_schedule(data):
    schedule = {}
    for key in MENU_SCHEDULE_KEYS:
        value = str(data.get(key, "") if hasattr(data, "get") else "").strip()
        if value:
            schedule[key] = value

    for key in ("date_start", "date_end"):
        if key in schedule and not parse_iso_date(schedule[key]):
            raise ValueError(f"Invalid {key}")
    for key in ("time_start", "time_end"):
        if key in schedule and parse_time_to_minutes(schedule[key]) is None:
            raise ValueError(f"Invalid {key}")
    return schedule


def build_daily_schedule(base_schedule, day, day_schedule=None):
    schedule = {
        key: value
        for key, value in (base_schedule or {}).items()
        if key in ("time_start", "time_end") and value
    }
    for key, value in (day_schedule or {}).items():
        if key in ("time_start", "time_end") and value:
            schedule[key] = value
    schedule["date_start"] = day.isoformat()
    schedule["date_end"] = day.isoformat()
    return schedule


def parse_week_start(value):
    parsed = parse_iso_date(value)
    if not parsed:
        return None
    return parsed - timedelta(days=parsed.weekday())


def _plain_text_key(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).strip().lower()


def _split_weekly_day_line(raw_line):
    line = str(raw_line or "").strip()
    if not line or ":" not in line:
        return None, ""
    day_part, menu_part = line.split(":", 1)
    day_index = WEEKDAY_ALIASES.get(_plain_text_key(day_part))
    return day_index, menu_part.strip()


def _sections_from_weekly_day_text(text):
    normalized = " ".join(str(text or "").replace(";", ",").split())
    if not normalized:
        return {}
    if "," in normalized:
        dishes = [" ".join(item.split()) for item in normalized.split(",") if item.strip()]
    else:
        dishes = normalized.split()
    sections = {}
    if dishes:
        sections["starter"] = dishes[0]
    if len(dishes) >= 2:
        sections["main"] = dishes[1]
    if len(dishes) >= 3:
        sections["dessert"] = " ".join(dishes[2:])
    return sections


def parse_weekly_menu_text(text):
    days = {}
    current_day = None
    for raw_line in str(text or "").splitlines():
        day_index, content = _split_weekly_day_line(raw_line)
        if day_index is not None:
            current_day = day_index
            if content:
                days[current_day] = " ".join([days.get(current_day, ""), content]).strip()
            continue
        if current_day is not None and raw_line.strip():
            days[current_day] = " ".join([days.get(current_day, ""), raw_line.strip()]).strip()
    return [
        {"index": index, "sections": sections}
        for index, sections in sorted(
            (
                (index, _sections_from_weekly_day_text(content))
                for index, content in days.items()
            ),
            key=lambda item: item[0],
        )
        if sections
    ]


def collect_weekly_menu_days(data):
    week_start = parse_week_start(data.get("week_start", "") if hasattr(data, "get") else "")
    if not week_start:
        return []
    text_days = parse_weekly_menu_text(data.get("weekly_menu_text", "") if hasattr(data, "get") else "")
    if text_days:
        return [
            {
                "index": day["index"],
                "date": week_start + timedelta(days=day["index"]),
                "sections": day["sections"],
            }
            for day in text_days
        ]
    days = []
    for index in range(7):
        sections = {}
        for key in WEEKDAY_SECTION_KEYS:
            value = str(data.get(f"week_{index}_{key}", "") if hasattr(data, "get") else "").strip()
            if value:
                sections[key] = value
        if sections:
            day_date = parse_iso_date(data.get(f"week_{index}_date", "") if hasattr(data, "get") else "") or week_start + timedelta(days=index)
            days.append({
                "index": index,
                "date": day_date,
                "sections": sections,
            })
    return days


def _schedule_has_expired(schedule, now=None):
    now = now or datetime.now()
    end_date = parse_iso_date((schedule or {}).get("date_end"))
    if not end_date:
        return False
    if end_date < now.date():
        return True
    if end_date > now.date():
        return False
    end_minutes = parse_time_to_minutes((schedule or {}).get("time_end"))
    if end_minutes is None:
        return False
    current_minutes = now.hour * 60 + now.minute
    return current_minutes > end_minutes


def _remove_generated_menu_references(cfg, filename):
    cfg["order"] = [item for item in cfg.get("order", []) if item != filename]
    cfg["disabled"] = [item for item in cfg.get("disabled", []) if item != filename]
    cfg.get("durations", {}).pop(filename, None)
    cfg.get("groups", {}).pop(filename, None)
    cfg.get("schedules", {}).pop(filename, None)
    cfg.get("generated_menus", {}).pop(filename, None)
    for screen_cfg in cfg.get("screens", {}).values():
        if not isinstance(screen_cfg, dict):
            continue
        screen_cfg["order"] = [item for item in screen_cfg.get("order", []) if item != filename]
        screen_cfg["disabled"] = [item for item in screen_cfg.get("disabled", []) if item != filename]
        screen_cfg.get("durations", {}).pop(filename, None)
        screen_cfg.get("schedules", {}).pop(filename, None)
    cleanup_orphan_group_metadata(cfg)


def cleanup_expired_generated_menus(now=None, username="system"):
    cfg = load_config()
    generated = cfg.get("generated_menus", {})
    if not isinstance(generated, dict) or not generated:
        return []

    deleted = []
    for filename, metadata in list(generated.items()):
        if not isinstance(metadata, dict) or not _schedule_has_expired(metadata.get("schedule", {}), now):
            continue
        safe_filename = os.path.basename(filename)
        path = os.path.join(UPLOAD_FOLDER, safe_filename)
        try:
            if os.path.exists(path):
                os.remove(path)
            delete_media_thumbnail(safe_filename)
            delete_image_variants(safe_filename)
            delete_video_variants(safe_filename)
        except OSError:
            continue
        _remove_generated_menu_references(cfg, safe_filename)
        deleted.append(safe_filename)
        log_activity(username, "delete", filename=safe_filename, details="menu expiré")

    if deleted:
        save_config(cfg)
        queue = load_queue()
        queue = [
            job for job in queue
            if not (job.get("filename") in deleted and job.get("status") == "pending")
        ]
        save_queue(queue)
    return deleted


def suggest_menu_items(lines, *, include_external=True, cache_external=False):
    items = []
    for line in lines:
        data = suggest_images(line, include_external=include_external, limit=6)
        suggestions = data.get("suggestions", [])
        if cache_external:
            suggestions = [_cache_external_suggestion(suggestion) for suggestion in suggestions]
        items.append({
            "text": line,
            "keywords": data.get("keywords", []),
            "suggestions": suggestions,
            "fallback": not bool(suggestions),
        })
    return items


def suggest_menu_lines(text, *, include_external=True, cache_external=False):
    return suggest_menu_items(parse_menu_lines(text), include_external=include_external, cache_external=cache_external)


def suggest_menu_sections(sections=None, *, fallback_text=None, include_external=True, cache_external=False):
    parsed_sections = parse_menu_sections(sections, fallback_text)
    grouped = []
    flat_items = []
    for section in parsed_sections:
        items = suggest_menu_items(section["lines"], include_external=include_external, cache_external=cache_external)
        for item in items:
            item["section"] = section["key"]
            item["section_label"] = section["label"]
        grouped.append({"key": section["key"], "label": section["label"], "items": items})
        flat_items.extend(items)
    return {"sections": grouped, "items": flat_items}


def _font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _fit_image(path, size):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)


def _blend_color(a, b, ratio):
    ratio = max(0.0, min(1.0, ratio))
    return tuple(int(a[idx] + (b[idx] - a[idx]) * ratio) for idx in range(3))


def _draw_modern_background(draw, phase=0):
    top = (255, 247, 237)
    bottom = (232, 245, 255)
    for y in range(MENU_SIZE[1]):
        ratio = y / max(1, MENU_SIZE[1] - 1)
        draw.line((0, y, MENU_SIZE[0], y), fill=_blend_color(top, bottom, ratio))
    draw.rounded_rectangle((-80, 42, 560, 258), radius=110, fill=(255, 221, 87))
    draw.rounded_rectangle((1390, -66, 2030, 218), radius=140, fill=(255, 159, 243))
    draw.rounded_rectangle((1260, 820, 1980, 1158), radius=170, fill=(126, 214, 223))
    draw.rounded_rectangle((-130, 790, 520, 1110), radius=150, fill=(186, 220, 88))
    for index, accent in enumerate(SECTION_ACCENTS * 2):
        offset = int(math.sin((phase + index * 5) * 0.16) * 18)
        x = 170 + (index * 315) % 1620 + offset
        y = 155 + ((index * 137) % 760)
        draw.ellipse((x, y, x + 30, y + 30), fill=accent)
        draw.line((x + 54, y + 12, x + 112, y + 12 + int(math.cos(phase * 0.2 + index) * 18)), fill=accent, width=8)
    for x in range(-80, MENU_SIZE[0], 180):
        y = 1000 + int(math.sin((phase + x) * 0.02) * 18)
        draw.arc((x, y, x + 80, y + 52), 180, 360, fill=(15, 23, 42), width=4)


def _draw_fallback(draw, box, text):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=34, fill=(255, 236, 153), outline=(15, 23, 42), width=4)
    keyword = extract_keywords(text)
    label = (keyword[0]["keyword"] if keyword else text[:1] or "?").upper()
    label = label[:2]
    font = _font(56, bold=True)
    bbox = draw.textbbox((0, 0), label, font=font)
    draw.text((x + (w - bbox[2]) / 2, y + (h - bbox[3]) / 2), label, font=font, fill=(15, 23, 42))


def _draw_wrapped(draw, text, x, y, width, font, fill, line_gap=8, max_lines=2):
    words = str(text or "").split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    for line in lines[:max_lines]:
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((0, 0), line, font=font)[3] + line_gap
    return y


def _draw_section_dish(canvas, draw, item, box, image_choices, *, accent=(148, 163, 184), active=False, pulse=0.0):
    x, y, w, h = box
    draw.rounded_rectangle((x + 8, y + 10, x + w + 8, y + h + 10), radius=30, fill=(211, 220, 232))
    fill = (255, 255, 255)
    outline = accent if active else (226, 232, 240)
    if active:
        glow = 4 + int(pulse * 6)
        draw.rounded_rectangle((x - glow, y - glow, x + w + glow, y + h + glow), radius=34, outline=accent, width=5)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=30, fill=fill, outline=outline, width=5 if active else 2)
    image_size = min(176, h - 28)
    image_box = (x + 16, y + 14, image_size, image_size)
    chosen = _safe_choice(image_choices.get(item["text"]))
    suggestion = chosen or next(
        (
            suggestion for suggestion in item["suggestions"]
            if suggestion.get("local_path") and os.path.exists(suggestion["local_path"])
        ),
        None,
    )
    if suggestion and suggestion.get("local_path") and os.path.exists(suggestion["local_path"]):
        thumb = _fit_image(suggestion["local_path"], (image_box[2], image_box[3]))
        mask = Image.new("L", (image_box[2], image_box[3]), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, image_box[2], image_box[3]), radius=32, fill=255)
        canvas.paste(thumb, (image_box[0], image_box[1]), mask)
        draw.rounded_rectangle((image_box[0], image_box[1], image_box[0] + image_box[2], image_box[1] + image_box[3]), radius=32, outline=(15, 23, 42), width=4)
    else:
        _draw_fallback(draw, image_box, item["text"])
    text_x = x + image_size + 42
    _draw_wrapped(draw, item["text"], text_x, y + 30, w - image_size - 62, _font(42, bold=True), (15, 23, 42), max_lines=2)
    keywords = ", ".join(k["keyword"] for k in item["keywords"][:3])
    if keywords:
        pill_w = min(w - image_size - 62, draw.textbbox((0, 0), keywords, font=_font(22, bold=True))[2] + 34)
        draw.rounded_rectangle((text_x, y + h - 48, text_x + pill_w, y + h - 16), radius=16, fill=_blend_color((255, 255, 255), accent, 0.24))
        draw.text((text_x + 17, y + h - 44), keywords, font=_font(22, bold=True), fill=(51, 65, 85))


def _dish_suggestion(item, image_choices):
    chosen = _safe_choice(image_choices.get(item["text"]))
    if chosen and chosen.get("local_path") and os.path.exists(chosen["local_path"]):
        return chosen
    return next(
        (
            suggestion for suggestion in item.get("suggestions", [])
            if suggestion.get("local_path") and os.path.exists(suggestion["local_path"])
        ),
        None,
    )


def _draw_food_hero(canvas, draw, item, image_choices, *, phase=0, accent=(255, 107, 107)):
    hero_box = (-24, 0, 1126, MENU_SIZE[1])
    suggestion = _dish_suggestion(item, image_choices) if item else None
    if suggestion:
        image = _fit_image(suggestion["local_path"], (hero_box[2] - hero_box[0] + 120, MENU_SIZE[1] + 120))
        pan_x = int(math.sin(phase * 0.055) * 28)
        pan_y = int(math.cos(phase * 0.04) * 22)
        canvas.paste(image, (hero_box[0] - 60 + pan_x, -60 + pan_y))
    else:
        for y in range(MENU_SIZE[1]):
            ratio = y / max(1, MENU_SIZE[1] - 1)
            color = _blend_color(_blend_color((255, 236, 153), accent, 0.22), _blend_color((255, 247, 237), accent, 0.52), ratio)
            draw.line((hero_box[0], y, hero_box[2], y), fill=color)
        for radius, mix in ((380, 0.14), (270, 0.2), (160, 0.28)):
            cx = 468 + int(math.sin(phase * 0.08) * 22)
            cy = 482 + int(math.cos(phase * 0.06) * 18)
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=_blend_color((255, 255, 255), accent, mix), width=24)
        _draw_fallback(draw, (382, 380, 260, 260), item["text"] if item else "Menu")

    overlay = Image.new("RGBA", MENU_SIZE, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for x in range(940):
        alpha = int(98 * (1 - x / 940))
        odraw.line((x, 0, x, MENU_SIZE[1]), fill=(15, 23, 42, alpha))
    odraw.rectangle((0, 0, 1120, MENU_SIZE[1]), fill=(15, 23, 42, 64))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB"))
    draw.rounded_rectangle((76, 790, 876, 930), radius=42, fill=(255, 255, 255), outline=(15, 23, 42), width=5)
    if item:
        _draw_wrapped(draw, item["text"], 106, 820, 720, _font(50, bold=True), (15, 23, 42), line_gap=4, max_lines=2)


def _draw_menu_item_row(draw, item, box, *, accent, active=False):
    x, y, w, h = box
    shadow = (213, 220, 231)
    draw.rounded_rectangle((x + 7, y + 9, x + w + 7, y + h + 9), radius=26, fill=shadow)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=26, fill=(255, 255, 255), outline=accent if active else (226, 232, 240), width=4 if active else 2)
    draw.ellipse((x + 24, y + 25, x + 76, y + 77), fill=accent)
    initial = " ".join(str(item.get("text", "?")).split())[:1].upper() or "?"
    bbox = draw.textbbox((0, 0), initial, font=_font(30, bold=True))
    draw.text((x + 50 - bbox[2] / 2, y + 35), initial, font=_font(30, bold=True), fill=(255, 255, 255))
    _draw_wrapped(draw, item.get("text", ""), x + 98, y + 20, w - 122, _font(31, bold=True), (15, 23, 42), line_gap=2, max_lines=2)


def _draw_compact_menu_section(draw, section, box, *, accent, active=False):
    x, y, w, h = box
    shadow = (213, 220, 231)
    draw.rounded_rectangle((x + 7, y + 9, x + w + 7, y + h + 9), radius=28, fill=shadow)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=28, fill=(255, 255, 255), outline=accent if active else (226, 232, 240), width=4 if active else 2)
    draw.rounded_rectangle((x + 22, y + 18, x + 180, y + 60), radius=21, fill=accent)
    draw.text((x + 44, y + 27), section.get("label", "Menu").upper(), font=_font(21, bold=True), fill=(255, 255, 255))

    items = section.get("items", [])[:4]
    if not items:
        _draw_wrapped(draw, "-", x + 30, y + 78, w - 60, _font(24, bold=True), (100, 116, 139), max_lines=1)
        return

    row_top = y + 70
    row_gap = 5
    row_h = max(24, min(44, (h - 82 - row_gap * (len(items) - 1)) // len(items)))
    for index, item in enumerate(items):
        row_y = row_top + index * (row_h + row_gap)
        dot_y = row_y + max(5, (row_h - 15) // 2)
        draw.ellipse((x + 30, dot_y, x + 45, dot_y + 15), fill=accent)
        _draw_wrapped(
            draw,
            item.get("text", ""),
            x + 62,
            row_y + max(2, (row_h - 25) // 2),
            w - 92,
            _font(22, bold=True),
            (15, 23, 42),
            line_gap=1,
            max_lines=1,
        )


def _render_menu_canvas(
    title,
    sections,
    image_choices,
    *,
    active_section_index=None,
    visible_section_count=None,
    section_reveal_progress=1.0,
    active_pulse=0.0,
    active_item_index=0,
    animation_phase=0,
    date_label=None,
):
    canvas = Image.new("RGB", MENU_SIZE, (255, 247, 237))
    draw = ImageDraw.Draw(canvas)
    _draw_modern_background(draw, animation_phase)
    title = " ".join(str(title or "Menu du jour").split())[:90] or "Menu du jour"
    date_text = " ".join(str(date_label or datetime.now().strftime("%d/%m/%Y")).split())

    if not sections:
        _draw_wrapped(draw, "Ajoutez une entrée, un plat ou un dessert.", 92, 320, 1100, _font(58, bold=True), (15, 23, 42))
        return canvas

    section_count = min(3, len(sections))
    active_idx = active_section_index if active_section_index is not None else 0
    active_idx = max(0, min(section_count - 1, active_idx))
    active_section = sections[active_idx]
    active_items = active_section.get("items", [])[:4]
    item_idx = max(0, min(len(active_items) - 1, int(active_item_index or 0))) if active_items else 0
    hero_item = active_items[item_idx] if active_items else None
    accent = SECTION_ACCENTS[active_idx % len(SECTION_ACCENTS)]
    reveal = max(0.0, min(1.0, float(section_reveal_progress)))
    panel_shift = int((1.0 - reveal) * 80)

    _draw_food_hero(canvas, draw, hero_item, image_choices, phase=animation_phase, accent=accent)
    draw.polygon([(1010, 0), (1920, 0), (1920, 1080), (900, 1080)], fill=(255, 247, 237))
    draw.line((990, 0, 900, 1080), fill=accent, width=11)

    panel_x = 1046 + panel_shift
    draw.rounded_rectangle((panel_x, 70, 1846, 1016), radius=58, fill=(255, 255, 255), outline=(15, 23, 42), width=5)
    draw.rounded_rectangle((panel_x + 46, 112, panel_x + 214, 174), radius=31, fill=accent)
    draw.text((panel_x + 78, 126), "MENU", font=_font(29, bold=True), fill=(255, 255, 255))
    date_box = draw.textbbox((0, 0), date_text, font=_font(28, bold=True))
    draw.text((panel_x + 734 - date_box[2], 128), date_text, font=_font(28, bold=True), fill=(71, 85, 105))
    _draw_wrapped(draw, title, panel_x + 46, 210, 680, _font(58, bold=True), (15, 23, 42), line_gap=4, max_lines=2)

    menu_top = 322
    menu_bottom = 932
    section_gap = 18
    section_h = (menu_bottom - menu_top - section_gap * (section_count - 1)) // section_count
    for section_index, section in enumerate(sections[:3]):
        section_y = menu_top + section_index * (section_h + section_gap)
        section_accent = SECTION_ACCENTS[section_index % len(SECTION_ACCENTS)]
        _draw_compact_menu_section(
            draw,
            section,
            (panel_x + 46, section_y, 700, section_h),
            accent=section_accent,
            active=section_index == active_idx,
        )

    nav_y = 956
    for section_index, section in enumerate(sections[:3]):
        dot_x = panel_x + 46 + section_index * 150
        dot_accent = SECTION_ACCENTS[section_index % len(SECTION_ACCENTS)]
        fill = dot_accent if section_index == active_idx else (226, 232, 240)
        draw.rounded_rectangle((dot_x, nav_y, dot_x + 112, nav_y + 18), radius=9, fill=fill)
    return canvas


def render_menu_image(title, text=None, *, sections=None, image_choices=None, date_label=None):
    image_choices = image_choices or {}
    menu_data = suggest_menu_sections(sections, fallback_text=text, include_external=True, cache_external=True)
    sections = [section for section in menu_data["sections"] if section["items"]]
    return _render_menu_canvas(title, sections, image_choices, date_label=date_label)


def _animation_duration_seconds(duration):
    return MENU_VIDEO_DURATION_SECONDS


def _active_animation_section_index(step, total_frames, section_count):
    section_count = max(1, int(section_count or 1))
    total_frames = max(1, int(total_frames or 1))
    frames_per_section = max(1, math.ceil(total_frames / section_count))
    return min(section_count - 1, max(0, int(step or 0) // frames_per_section))


def _active_animation_item_index(step, total_frames, section_count, item_count):
    item_count = max(1, int(item_count or 1))
    section_count = max(1, int(section_count or 1))
    total_frames = max(1, int(total_frames or 1))
    frames_per_section = max(1, math.ceil(total_frames / section_count))
    section_start = _active_animation_section_index(step, total_frames, section_count) * frames_per_section
    section_step = max(0, int(step or 0) - section_start)
    frames_per_item = max(1, math.ceil(frames_per_section / item_count))
    return min(item_count - 1, section_step // frames_per_item)


def render_menu_animation(title, text=None, *, sections=None, image_choices=None, destination=None, duration=None, date_label=None):
    image_choices = image_choices or {}
    menu_data = suggest_menu_sections(sections, fallback_text=text, include_external=True, cache_external=True)
    grouped_sections = [section for section in menu_data["sections"] if section["items"]]
    if not grouped_sections or not destination:
        return False

    total_seconds = _animation_duration_seconds(duration)
    fps = 8
    section_count = min(3, len(grouped_sections))
    total_frames = total_seconds * fps

    with tempfile.TemporaryDirectory(prefix="visio-menu-animation-") as tmp_dir:
        frame_index = 0
        for step in range(total_frames):
            active_index = _active_animation_section_index(step, total_frames, section_count)
            active_items = grouped_sections[active_index].get("items", [])[:4]
            active_item_index = _active_animation_item_index(step, total_frames, section_count, len(active_items))
            pulse = 0.45 + 0.35 * (1.0 + math.sin(step * 0.55)) / 2
            frame = _render_menu_canvas(
                title,
                grouped_sections,
                image_choices,
                active_section_index=active_index,
                active_item_index=active_item_index,
                active_pulse=pulse,
                animation_phase=step,
                date_label=date_label,
            )
            frame.save(os.path.join(tmp_dir, f"frame_{frame_index:04d}.png"), "PNG", optimize=True)
            frame_index += 1

        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-framerate", str(fps),
                    "-i", os.path.join(tmp_dir, "frame_%04d.png"),
                    "-vf", "format=yuv420p",
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-movflags", "+faststart",
                    "-r", "24",
                    destination,
                ],
                capture_output=True,
                check=True,
            )
            return os.path.exists(destination)
        except Exception:
            return False


def create_menu_from_text(title, text=None, *, sections=None, duration=None, schedule=None, screens=None, username=None, image_choices=None, date_label=None, filename=None):
    parsed_choices = parse_menu_image_choices(image_choices)
    stem = clean_filename("menu_" + (title or "du_jour").lower()) or "menu"
    dated = datetime.now().strftime("%Y%m%d_%H%M")
    filename = os.path.basename(filename) if filename else ensure_unique_filename(UPLOAD_FOLDER, f"{stem}_{dated}.mp4")
    destination = os.path.join(UPLOAD_FOLDER, filename)
    animated = render_menu_animation(title, text, sections=sections, image_choices=parsed_choices, destination=destination, duration=duration, date_label=date_label)
    if not animated:
        filename = ensure_unique_filename(UPLOAD_FOLDER, f"{stem}_{dated}.png")
        destination = os.path.join(UPLOAD_FOLDER, filename)
        image = render_menu_image(title, text, sections=sections, image_choices=parsed_choices, date_label=date_label)
        image.save(destination, "PNG", optimize=True)
    generate_standard_renditions(filename)

    cfg = load_config()
    if animated:
        cfg.setdefault("durations", {})[filename] = MENU_VIDEO_DURATION_SECONDS
    elif duration:
        try:
            cfg.setdefault("durations", {})[filename] = max(1, min(3600, int(duration)))
        except (TypeError, ValueError):
            pass
    selected_screens = [str(screen or "").strip().lower() for screen in (screens or [])]
    if not selected_screens:
        selected_screens = ["__default__"]
    if "__default__" in selected_screens:
        order = cfg.setdefault("order", [])
        if filename not in order:
            order.append(filename)
        if schedule:
            cfg.setdefault("schedules", {})[filename] = dict(schedule)
    for screen in selected_screens:
        if screen == "__default__":
            continue
        if screen in cfg.get("screens", {}):
            order = cfg["screens"][screen].setdefault("order", [])
            if filename not in order:
                order.append(filename)
            if schedule:
                cfg["screens"][screen].setdefault("schedules", {})[filename] = dict(schedule)
    cfg.setdefault("generated_menus", {})[filename] = {
        "created_at": datetime.now().isoformat(timespec="minutes"),
        "duration_locked": bool(animated),
        "duration": MENU_VIDEO_DURATION_SECONDS if animated else cfg.get("durations", {}).get(filename),
        "schedule": dict(schedule or {}),
        "screens": selected_screens,
    }
    save_config(cfg)
    log_activity(username, "upload", filename=filename, details="menu rapide")
    return filename


def _queued_filenames():
    try:
        return {
            os.path.basename(job.get("filename", ""))
            for job in load_queue()
            if job.get("status") in ("pending", "processing")
        }
    except Exception:
        return set()


def _planned_menu_filename(title, date_suffix=None):
    stem = clean_filename("menu_" + (title or "du_jour").lower()) or "menu"
    suffix = date_suffix or datetime.now().strftime("%Y%m%d_%H%M")
    filename = ensure_unique_filename(UPLOAD_FOLDER, f"{stem}_{suffix}.mp4")
    queued = _queued_filenames()
    if filename not in queued:
        return filename
    base, ext = os.path.splitext(filename)
    counter = 2
    while f"{base}_{counter}{ext}" in queued or os.path.exists(os.path.join(UPLOAD_FOLDER, f"{base}_{counter}{ext}")):
        counter += 1
    return f"{base}_{counter}{ext}"


def enqueue_menu_from_text(title, text=None, *, sections=None, duration=None, schedule=None, screens=None, username=None, image_choices=None, date_label=None):
    filename = _planned_menu_filename(title)
    enqueue_menu_generation_job(filename, {
        "title": title,
        "text": text,
        "sections": sections,
        "duration": duration,
        "schedule": schedule,
        "screens": screens,
        "username": username,
        "image_choices": image_choices,
        "date_label": date_label,
    })
    log_activity(username, "compress", filename=filename, details="menu ajouté à la file")
    return filename


def process_queued_menu_generation(filename, payload):
    return create_menu_from_text(
        payload.get("title"),
        sections=payload.get("sections"),
        duration=payload.get("duration"),
        schedule=payload.get("schedule"),
        screens=payload.get("screens"),
        username=payload.get("username") or "system",
        image_choices=payload.get("image_choices"),
        date_label=payload.get("date_label"),
        filename=filename,
    )


def create_weekly_menus_from_form(title, form, *, duration=None, schedule=None, screens=None, username=None, image_choices=None, queue_generation=False):
    days = collect_weekly_menu_days(form)
    if not days:
        raise ValueError("No weekly menu day provided")
    created = []
    for day in days:
        day_label = WEEKDAY_TITLES[day["index"]]
        date_label = day["date"].strftime("%d/%m/%Y")
        day_title = f"{title or 'Menu'} - {day_label}"
        daily_schedule = build_daily_schedule(schedule, day["date"], day.get("schedule"))
        if queue_generation:
            filename = _planned_menu_filename(day_title, day["date"].strftime("%Y%m%d"))
            enqueue_menu_generation_job(filename, {
                "title": day_title,
                "sections": day["sections"],
                "duration": duration,
                "schedule": daily_schedule,
                "screens": screens,
                "username": username,
                "image_choices": image_choices,
                "date_label": date_label,
            })
            created.append(filename)
        else:
            created.append(create_menu_from_text(
                day_title,
                sections=day["sections"],
                duration=duration,
                schedule=daily_schedule,
                screens=screens,
                username=username,
                image_choices=image_choices,
                date_label=date_label,
            ))
    return created
