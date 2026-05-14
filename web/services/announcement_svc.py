# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import base64
import io
import os
import re
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from constants import IMAGES_FOLDER, UPLOAD_FOLDER
from services.activity_svc import log_activity
from services.config_svc import load_config, save_config
from services.media_svc import clean_filename, ensure_unique_filename, generate_standard_renditions, get_all_media


ANNOUNCEMENT_SIZE = (1920, 1080)
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"
ALLOWED_IMAGE_HOSTS = {"upload.wikimedia.org", "commons.wikimedia.org"}
COMMONS_RASTER_MIMES = {"image/jpeg", "image/png", "image/webp"}


def _font(size, bold=False):
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
    )
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def _hex_to_rgb(value, fallback):
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in raw):
        return tuple(int(raw[idx:idx + 2], 16) for idx in (0, 2, 4))
    return fallback


def _cover(image, size=ANNOUNCEMENT_SIZE):
    frame = ImageOps.exif_transpose(image).convert("RGB")
    return ImageOps.fit(frame, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _safe_image_url(url):
    parsed = urlparse(str(url or ""))
    return parsed.scheme == "https" and parsed.hostname in ALLOWED_IMAGE_HOSTS


def _plain_text(value):
    return " ".join(re.sub(r"<[^>]*>", " ", str(value or "")).split())


def _download_image(url):
    if not _safe_image_url(url):
        raise ValueError("URL externe non autorisée.")
    response = requests.get(
        url,
        timeout=12,
        headers={"User-Agent": "Visio-Display/announcement-builder"},
    )
    response.raise_for_status()
    if not _safe_image_url(response.url):
        raise ValueError("Redirection externe non autorisée.")
    content_type = response.headers.get("Content-Type", "")
    if not content_type.startswith("image/"):
        raise ValueError("Le fichier externe n'est pas une image.")
    if len(response.content) > 18 * 1024 * 1024:
        raise ValueError("L'image externe est trop volumineuse.")
    with Image.open(io.BytesIO(response.content)) as image:
        return image.copy()


def fetch_thumbnail_bytes(url, *, max_bytes=16 * 1024 * 1024):
    if not _safe_image_url(url):
        raise ValueError("URL externe non autorisée.")
    response = requests.get(
        url,
        timeout=(2, 5),
        headers={"User-Agent": "Visio-Display/announcement-builder"},
    )
    response.raise_for_status()
    if not _safe_image_url(response.url):
        raise ValueError("Redirection externe non autorisée.")
    if len(response.content) > max_bytes:
        raise ValueError("La vignette externe est trop volumineuse.")
    with Image.open(io.BytesIO(response.content)) as image:
        thumb = ImageOps.exif_transpose(image).convert("RGB")
        thumb.thumbnail((480, 270), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        thumb.save(output, "JPEG", quality=86, optimize=True)
        return output.getvalue()


def _thumbnail_data_uri(*urls):
    for url in urls:
        if not _safe_image_url(url):
            continue
        try:
            encoded = base64.b64encode(fetch_thumbnail_bytes(url)).decode("ascii")
            return f"data:image/jpeg;base64,{encoded}"
        except Exception:
            continue
    return ""


def _attach_thumbnail_data(candidates):
    if not candidates:
        return []
    max_workers = min(8, len(candidates))
    results_by_index = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_thumbnail_data_uri, candidate["thumb_url"]): index
            for index, candidate in enumerate(candidates)
        }
        for future in as_completed(futures):
            index = futures[future]
            thumb_data = future.result()
            if thumb_data:
                candidate = dict(candidates[index])
                candidate["thumb_data"] = thumb_data
                results_by_index[index] = candidate
    return [results_by_index[index] for index in sorted(results_by_index)]


def _media_background(filename):
    filename = os.path.basename(str(filename or ""))
    if not filename:
        return None
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return None
    with Image.open(path) as image:
        return image.copy()


def build_background(form, uploaded_file=None):
    mode = str(form.get("background_mode") or "color").strip()
    color = _hex_to_rgb(form.get("background_color"), (30, 41, 59))
    if mode == "upload" and uploaded_file and uploaded_file.filename:
        with Image.open(uploaded_file.stream) as image:
            return _cover(image)
    if mode == "media":
        image = _media_background(form.get("background_media"))
        if image:
            return _cover(image)
    if mode == "external":
        image = _download_image(form.get("external_url"))
        return _cover(image)
    return Image.new("RGB", ANNOUNCEMENT_SIZE, color)


def _draw_wrapped(draw, text, box, font, fill, spacing=12, max_lines=5):
    x, y, width, _height = box
    words = str(text or "").split()
    if not words:
        return y
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((0, 0), line, font=font)[3] + spacing
    return y


def _draw_logo(canvas, app_name, text_color):
    cfg = load_config()
    logo = cfg.get("logo", "")
    logo_path = os.path.join(IMAGES_FOLDER, logo)
    if logo and os.path.exists(logo_path) and logo.lower().endswith((".png", ".jpg", ".jpeg")):
        try:
            with Image.open(logo_path) as logo_img:
                mark = ImageOps.exif_transpose(logo_img).convert("RGBA")
                mark.thumbnail((190, 80), Image.Resampling.LANCZOS)
                canvas.paste(mark, (96, 78), mark)
                return
        except Exception:
            pass
    draw = ImageDraw.Draw(canvas)
    draw.text((96, 84), app_name or "Visio", font=_font(34, bold=True), fill=text_color)


def _template_layout(canvas, form):
    draw = ImageDraw.Draw(canvas)
    app_name = load_config().get("app_name", "Visio")
    text_color = _hex_to_rgb(form.get("text_color"), (255, 255, 255))
    accent = _hex_to_rgb(form.get("accent_color"), (124, 58, 237))
    template = str(form.get("template_style") or "info").strip()
    title = str(form.get("title") or "").strip()
    body = str(form.get("body") or "").strip()
    date_text = str(form.get("date_text") or "").strip()
    place = str(form.get("place") or "").strip()
    external_credit = str(form.get("external_credit") or "").strip()

    overlay = max(0, min(85, int(form.get("overlay_strength") or 35)))
    if overlay:
        veil = Image.new("RGBA", ANNOUNCEMENT_SIZE, (0, 0, 0, int(255 * overlay / 100)))
        canvas.alpha_composite(veil)

    if template == "urgent":
        draw.rounded_rectangle((86, 82, 420, 150), radius=10, fill=accent + (245,))
        draw.text((116, 101), "URGENT", font=_font(34, bold=True), fill=(255, 255, 255))
        title_font = _font(104, bold=True)
        body_font = _font(50)
        start_y = 300
    elif template == "event":
        draw.rounded_rectangle((92, 250, 430, 820), radius=22, fill=accent + (225,))
        when = date_text or "DATE"
        wrapped = textwrap.wrap(when.upper(), width=9)[:3]
        y = 360
        for line in wrapped:
            bbox = draw.textbbox((0, 0), line, font=_font(66, bold=True))
            draw.text((260 - (bbox[2] / 2), y), line, font=_font(66, bold=True), fill=(255, 255, 255))
            y += 86
        title_font = _font(78, bold=True)
        body_font = _font(42)
        start_y = 310
        _draw_logo(canvas, app_name, text_color)
        _draw_wrapped(draw, title.upper(), (520, start_y, 1180, 260), title_font, text_color, spacing=18, max_lines=3)
        y = _draw_wrapped(draw, body, (525, 560, 1160, 230), body_font, text_color, spacing=12, max_lines=4)
        if place:
            draw.text((525, max(y + 16, 815)), place, font=_font(36, bold=True), fill=text_color)
        if external_credit:
            credit = external_credit[:120]
            bbox = draw.textbbox((0, 0), credit, font=_font(20))
            draw.text((1888 - bbox[2], 1038), credit, font=_font(20), fill=tuple(min(255, int(ch * 0.82)) for ch in text_color))
        return
    else:
        _draw_logo(canvas, app_name, text_color)
        title_font = _font(86, bold=True)
        body_font = _font(44)
        start_y = 330

    y = _draw_wrapped(draw, title.upper(), (112, start_y, 1500, 280), title_font, text_color, spacing=20, max_lines=3)
    y = max(y + 18, start_y + 220)
    y = _draw_wrapped(draw, body, (118, y, 1340, 280), body_font, text_color, spacing=14, max_lines=5)
    footer = "  ·  ".join(part for part in (date_text, place) if part)
    if footer:
        draw.rounded_rectangle((112, 894, 112 + min(1320, 34 * len(footer)), 960), radius=10, fill=accent + (210,))
        draw.text((142, 910), footer, font=_font(36, bold=True), fill=text_color)
    if external_credit:
        credit = external_credit[:120]
        bbox = draw.textbbox((0, 0), credit, font=_font(20))
        draw.text((1888 - bbox[2], 1038), credit, font=_font(20), fill=tuple(min(255, int(ch * 0.82)) for ch in text_color))


def create_announcement(form, uploaded_file=None, username=None):
    title = str(form.get("title") or "").strip()
    if not title:
        raise ValueError("Le titre est obligatoire.")

    background = build_background(form, uploaded_file).convert("RGBA")
    blur = max(0, min(18, int(form.get("background_blur") or 0)))
    if blur:
        background = background.filter(ImageFilter.GaussianBlur(blur))
    brightness = max(40, min(140, int(form.get("background_brightness") or 100)))
    if brightness != 100:
        background = ImageEnhance.Brightness(background).enhance(brightness / 100)

    _template_layout(background, form)

    stem = clean_filename("annonce_" + title.lower()) or "annonce"
    dated = datetime.now().strftime("%Y%m%d_%H%M")
    filename = ensure_unique_filename(UPLOAD_FOLDER, f"{stem}_{dated}.png")
    destination = os.path.join(UPLOAD_FOLDER, filename)
    background.convert("RGB").save(destination, "PNG", optimize=True)
    generate_standard_renditions(filename)

    cfg = load_config()
    cfg.setdefault("order", [])
    if filename not in cfg["order"]:
        cfg["order"].append(filename)

    duration = str(form.get("duration") or "").strip()
    if duration:
        try:
            cfg.setdefault("durations", {})[filename] = max(1, min(3600, int(duration)))
        except ValueError:
            pass

    for screen in form.getlist("screens"):
        screen = str(screen or "").strip().lower()
        if screen in cfg.get("screens", {}):
            order = cfg["screens"][screen].setdefault("order", [])
            if filename not in order:
                order.append(filename)

    save_config(cfg)
    details = "announcement"
    if form.get("external_credit"):
        details = f"announcement; bg credit: {str(form.get('external_credit'))[:180]}"
    log_activity(username, "upload", filename=filename, details=details)
    return filename


def commons_search(query, limit=12):
    query = str(query or "").strip()
    if not query:
        return []
    target_limit = max(1, min(24, int(limit or 12)))
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrnamespace": "6",
        "gsrsearch": query,
        "gsrlimit": max(target_limit, min(30, target_limit * 3)),
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": 480,
        "iiurlheight": 270,
        "origin": "*",
    }
    response = requests.get(COMMONS_API_URL, params=params, timeout=10, headers={"User-Agent": "Visio-Display/announcement-builder"})
    response.raise_for_status()
    pages = response.json().get("query", {}).get("pages", {})
    candidates = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") not in COMMONS_RASTER_MIMES:
            continue
        url = info.get("url") or ""
        thumb = info.get("thumburl") or url
        if not _safe_image_url(url) or not _safe_image_url(thumb):
            continue
        meta = info.get("extmetadata") or {}
        license_name = _plain_text((meta.get("LicenseShortName") or {}).get("value") or "")
        artist = _plain_text((meta.get("Artist") or {}).get("value") or "")
        credit = " ".join(textwrap.wrap(f"{license_name} {artist}".strip(), width=90))[:180]
        title = str(page.get("title") or "").replace("File:", "")
        candidates.append({
            "title": title,
            "url": url,
            "thumb_url": thumb,
            "credit": credit,
            "source": "wikimedia",
        })
        if len(candidates) >= max(target_limit, min(30, target_limit * 2)):
            break
    return _attach_thumbnail_data(candidates)[:target_limit]


def image_media_choices():
    return [filename for filename in get_all_media() if filename.lower().endswith((".jpg", ".jpeg", ".png"))]
