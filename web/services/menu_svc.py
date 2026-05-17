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
MENU_SECTIONS = (
    ("starter", "Entrée"),
    ("main", "Plat"),
    ("dessert", "Dessert"),
)
SECTION_ACCENTS = (
    (34, 211, 238),
    (244, 114, 182),
    (163, 230, 53),
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
        image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", size, (235, 239, 246))
        canvas.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
        return canvas


def _blend_color(a, b, ratio):
    ratio = max(0.0, min(1.0, ratio))
    return tuple(int(a[idx] + (b[idx] - a[idx]) * ratio) for idx in range(3))


def _draw_modern_background(draw, phase=0):
    top = (12, 18, 32)
    bottom = (30, 41, 59)
    for y in range(MENU_SIZE[1]):
        ratio = y / max(1, MENU_SIZE[1] - 1)
        draw.line((0, y, MENU_SIZE[0], y), fill=_blend_color(top, bottom, ratio))
    for index, accent in enumerate(SECTION_ACCENTS):
        offset = int(math.sin((phase + index * 9) * 0.18) * 36)
        x = 170 + index * 610 + offset
        y = 250 + int(math.cos((phase + index * 7) * 0.14) * 42)
        for radius, mix in ((300, 0.12), (220, 0.16), (140, 0.2)):
            color = _blend_color((18, 24, 38), accent, mix)
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=18)
    for x in range(-260, MENU_SIZE[0] + 260, 260):
        drift = int((phase * 7) % 260)
        draw.line((x + drift, 1080, x + drift + 520, 0), fill=(42, 53, 77), width=2)


def _draw_fallback(draw, box, text):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=28, fill=(15, 23, 42), outline=(71, 85, 105), width=3)
    keyword = extract_keywords(text)
    label = (keyword[0]["keyword"] if keyword else text[:1] or "?").upper()
    font = _font(48, bold=True)
    bbox = draw.textbbox((0, 0), label, font=font)
    draw.text((x + (w - bbox[2]) / 2, y + (h - bbox[3]) / 2), label, font=font, fill=(226, 232, 240))


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
    fill = _blend_color((15, 23, 42), accent, 0.08 if active else 0.035)
    outline = _blend_color((51, 65, 85), accent, 0.45 if active else 0.16)
    if active:
        glow = 6 + int(pulse * 9)
        draw.rounded_rectangle((x - glow, y - glow, x + w + glow, y + h + glow), radius=22, outline=_blend_color((15, 23, 42), accent, 0.85), width=3)
    draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill=fill, outline=outline, width=3 if active else 2)
    image_size = min(146, h - 28)
    image_box = (x + 14, y + 14, image_size, image_size)
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
        canvas.paste(thumb, (image_box[0], image_box[1]))
        draw.rounded_rectangle((image_box[0], image_box[1], image_box[0] + image_box[2], image_box[1] + image_box[3]), radius=18, outline=_blend_color((255, 255, 255), accent, 0.55), width=3)
    else:
        _draw_fallback(draw, image_box, item["text"])
    text_x = x + image_size + 34
    _draw_wrapped(draw, item["text"], text_x, y + 34, w - image_size - 54, _font(34, bold=True), (248, 250, 252), max_lines=2)
    keywords = ", ".join(k["keyword"] for k in item["keywords"][:3])
    if keywords:
        draw.text((text_x, y + h - 42), keywords, font=_font(21), fill=(148, 163, 184))


def _render_menu_canvas(
    title,
    sections,
    image_choices,
    *,
    active_section_index=None,
    visible_section_count=None,
    section_reveal_progress=1.0,
    active_pulse=0.0,
    animation_phase=0,
    date_label=None,
):
    canvas = Image.new("RGB", MENU_SIZE, (12, 18, 32))
    draw = ImageDraw.Draw(canvas)
    _draw_modern_background(draw, animation_phase)
    title = " ".join(str(title or "Menu du jour").split())[:90] or "Menu du jour"
    draw.rounded_rectangle((70, 38, 1850, 142), radius=32, fill=(15, 23, 42), outline=(51, 65, 85), width=2)
    draw.line((104, 132, 520, 132), fill=SECTION_ACCENTS[animation_phase % len(SECTION_ACCENTS)], width=5)
    draw.text((104, 62), title, font=_font(54, bold=True), fill=(255, 255, 255))
    date_text = " ".join(str(date_label or datetime.now().strftime("%d/%m/%Y")).split())
    date_box = draw.textbbox((0, 0), date_text, font=_font(34, bold=True))
    draw.text((1800 - date_box[2], 70), date_text, font=_font(34, bold=True), fill=(203, 213, 225))

    if not sections:
        _draw_wrapped(draw, "Ajoutez une entrée, un plat ou un dessert.", 92, 320, 1100, _font(58, bold=True), (226, 232, 240))
        return canvas

    section_gap = 34
    section_w = (1736 - section_gap * 2) // 3
    section_y = 210
    section_h = 790
    for section_index, section in enumerate(sections[:3]):
        if visible_section_count is not None and section_index >= visible_section_count:
            continue
        x = 92 + section_index * (section_w + section_gap)
        current_section_y = section_y
        if active_section_index == section_index:
            reveal = max(0.0, min(1.0, float(section_reveal_progress)))
            current_section_y += int((1.0 - reveal) * 72)
        is_active = active_section_index is None or section_index == active_section_index
        accent = SECTION_ACCENTS[section_index % len(SECTION_ACCENTS)]
        fill = _blend_color((15, 23, 42), accent, 0.11 if is_active else 0.045)
        outline = _blend_color((71, 85, 105), accent, 0.9 if is_active else 0.22)
        width = 6 + int(active_pulse * 8) if active_section_index == section_index else 2
        if active_section_index == section_index:
            for glow_pad, mix in ((28, 0.35), (16, 0.58), (8, 0.9)):
                draw.rounded_rectangle(
                    (x - glow_pad, current_section_y - glow_pad, x + section_w + glow_pad, current_section_y + section_h + glow_pad),
                    radius=32,
                    outline=_blend_color((15, 23, 42), accent, mix),
                    width=max(2, int(2 + active_pulse * 3)),
                )
        draw.rounded_rectangle((x, current_section_y, x + section_w, current_section_y + section_h), radius=22, fill=fill, outline=outline, width=width)
        header_fill = _blend_color((15, 23, 42), accent, 0.72)
        draw.rounded_rectangle((x + 18, current_section_y + 18, x + section_w - 18, current_section_y + 78), radius=18, fill=header_fill, outline=_blend_color((255, 255, 255), accent, 0.6), width=2)
        draw.text((x + 38, current_section_y + 29), section["label"].upper(), font=_font(34, bold=True), fill=(255, 255, 255))
        dish_y = current_section_y + 98
        available = section_h - 126
        visible_items = section["items"][:4]
        if not visible_items:
            break
        dish_gap = 18
        dish_h = min(176, (available - dish_gap * (len(visible_items) - 1)) // len(visible_items))
        for item_index, item in enumerate(visible_items):
            y = dish_y + item_index * (dish_h + dish_gap)
            _draw_section_dish(
                canvas,
                draw,
                item,
                (x + 18, y, section_w - 36, dish_h),
                image_choices,
                accent=accent,
                active=is_active,
                pulse=active_pulse,
            )
    return canvas


def render_menu_image(title, text=None, *, sections=None, image_choices=None, date_label=None):
    image_choices = image_choices or {}
    menu_data = suggest_menu_sections(sections, fallback_text=text, include_external=True, cache_external=True)
    sections = [section for section in menu_data["sections"] if section["items"]]
    return _render_menu_canvas(title, sections, image_choices, date_label=date_label)


def _animation_duration_seconds(duration):
    try:
        seconds = int(duration)
    except (TypeError, ValueError):
        seconds = 15
    return max(6, min(15, seconds))


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
            active_index = (step // max(1, fps)) % section_count
            local_step = step % max(1, fps)
            blink = 1.0 if local_step in (0, 1, 4) else 0.22
            flicker = 0.35 * (1.0 + math.sin(step * 2.7))
            pulse = max(0.18, min(1.0, blink + flicker))
            frame = _render_menu_canvas(
                title,
                grouped_sections,
                image_choices,
                active_section_index=active_index,
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
    if duration:
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
        "schedule": dict(schedule or {}),
        "screens": selected_screens,
    }
    save_config(cfg)
    log_activity(username, "upload", filename=filename, details="menu rapide")
    return filename


def _planned_menu_filename(title, day):
    stem = clean_filename("menu_" + (title or "semaine").lower()) or "menu"
    return ensure_unique_filename(UPLOAD_FOLDER, f"{stem}_{day.strftime('%Y%m%d')}.mp4")


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
            filename = _planned_menu_filename(day_title, day["date"])
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
