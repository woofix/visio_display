# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import base64
import io
import os
from datetime import datetime
from urllib.parse import quote_plus

import qrcode
from PIL import Image, ImageColor
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_M

from constants import UPLOAD_FOLDER
from services.activity_svc import log_activity
from services.i18n import _t
from services.media_svc import clean_filename, ensure_unique_filename, generate_standard_renditions, get_media_url
from services.playlist_cache_svc import bump_media_revision


QR_TYPES = {
    "url",
    "wifi",
    "phone",
    "sms",
    "vcard",
    "maps",
    "whatsapp",
    "text",
    "youtube",
    "pdf",
}
WIFI_SECURITY_MAP = {
    "wpa": "WPA",
    "wpa2": "WPA",
    "wpa3": "WPA",
    "wep": "WEP",
    "none": "nopass",
    "nopass": "nopass",
}


def _as_text(value, max_len=2048):
    return str(value or "").strip()[:max_len]


def _required(value, key):
    text = _as_text(value)
    if not text:
        raise ValueError(_t(key))
    return text


def _escape_wifi(value):
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace(":", "\\:")
        .replace('"', '\\"')
    )


def _url(value, *, required_key="qr_error_url_required"):
    text = _required(value, required_key)
    if "://" not in text:
        text = "https://" + text
    if not text.lower().startswith(("http://", "https://")):
        raise ValueError(_t("qr_error_url_invalid"))
    return text


def build_qr_payload(data):
    qr_type = _as_text(data.get("type"), 32).lower()
    if qr_type not in QR_TYPES:
        raise ValueError(_t("qr_error_type_invalid"))

    if qr_type == "wifi":
        ssid = _required(data.get("ssid"), "qr_error_ssid_required")
        security = _as_text(data.get("security"), 16).lower() or "wpa"
        auth = WIFI_SECURITY_MAP.get(security)
        if not auth:
            raise ValueError(_t("qr_error_security_invalid"))
        password = _as_text(data.get("password"), 256)
        if auth != "nopass" and not password:
            raise ValueError(_t("qr_error_password_required"))
        hidden = "true" if bool(data.get("hidden")) else "false"
        parts = [f"T:{auth}", f"S:{_escape_wifi(ssid)}"]
        if auth != "nopass":
            parts.append(f"P:{_escape_wifi(password)}")
        if bool(data.get("hidden")):
            parts.append(f"H:{hidden}")
        return "WIFI:" + ";".join(parts) + ";;"

    if qr_type == "url":
        return _url(data.get("url"))
    if qr_type == "pdf":
        return _url(data.get("url"), required_key="qr_error_pdf_required")
    if qr_type == "youtube":
        value = _required(data.get("url"), "qr_error_youtube_required")
        if value.startswith(("http://", "https://")):
            return value
        return "https://www.youtube.com/watch?v=" + quote_plus(value)
    if qr_type == "phone":
        return "TEL:" + _required(data.get("phone"), "qr_error_phone_required")
    if qr_type == "sms":
        phone = _required(data.get("phone"), "qr_error_phone_required")
        return f"SMSTO:{phone}:{_as_text(data.get('message'), 600)}"
    if qr_type == "whatsapp":
        phone = _required(data.get("phone"), "qr_error_phone_required")
        normalized = "".join(ch for ch in phone if ch.isdigit())
        if not normalized:
            raise ValueError(_t("qr_error_phone_required"))
        message = _as_text(data.get("message"), 600)
        suffix = f"?text={quote_plus(message)}" if message else ""
        return f"https://wa.me/{normalized}{suffix}"
    if qr_type == "maps":
        query = _required(data.get("query"), "qr_error_maps_required")
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)
    if qr_type == "vcard":
        name = _required(data.get("name"), "qr_error_contact_required")
        lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{name}"]
        if _as_text(data.get("phone")):
            lines.append(f"TEL:{_as_text(data.get('phone'))}")
        if _as_text(data.get("email")):
            lines.append(f"EMAIL:{_as_text(data.get('email'))}")
        if _as_text(data.get("organization")):
            lines.append(f"ORG:{_as_text(data.get('organization'))}")
        if _as_text(data.get("url")):
            lines.append(f"URL:{_url(data.get('url'))}")
        lines.append("END:VCARD")
        return "\n".join(lines)
    return _required(data.get("text"), "qr_error_text_required")


def _color(value, fallback):
    try:
        return ImageColor.getrgb(str(value or fallback))
    except ValueError:
        return ImageColor.getrgb(fallback)


def _transparent_background(image, background_rgb):
    pixels = image.load()
    width, height = image.size
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a and (r, g, b) == background_rgb:
                pixels[x, y] = (r, g, b, 0)
    return image


def _paste_logo(image, logo_path):
    if not logo_path or not os.path.exists(logo_path):
        return image
    try:
        with Image.open(logo_path) as logo:
            logo = logo.convert("RGBA")
            target = max(32, int(min(image.size) * 0.22))
            logo.thumbnail((target, target), Image.Resampling.LANCZOS)
            pad = max(8, target // 9)
            box = Image.new("RGBA", (logo.width + pad * 2, logo.height + pad * 2), (255, 255, 255, 235))
            box.alpha_composite(logo, (pad, pad))
            pos = ((image.width - box.width) // 2, (image.height - box.height) // 2)
            image.alpha_composite(box, pos)
    except Exception:
        pass
    return image


def render_qr_image(data, *, logo_path=None):
    payload = build_qr_payload(data)
    size = max(160, min(1600, int(data.get("size") or 640)))
    margin = max(0, min(8, int(data.get("margin") or 4)))
    foreground = _color(data.get("foreground"), "#111827")
    background = _color(data.get("background"), "#ffffff")
    transparent = bool(data.get("transparent"))

    box_size = 12
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H if logo_path else ERROR_CORRECT_M,
        box_size=box_size,
        border=margin,
    )
    qr.add_data(payload.encode("utf-8"))
    qr.make(fit=True)
    image = qr.make_image(fill_color=foreground, back_color=background).convert("RGBA")
    if transparent:
        image = _transparent_background(image, background)
    image = image.resize((size, size), Image.Resampling.NEAREST)
    image = _paste_logo(image, logo_path)
    return image, payload


def image_to_data_url(image):
    output = io.BytesIO()
    image.save(output, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def save_qr_media(image, data, *, username=None):
    qr_type = _as_text(data.get("type"), 32).lower() or "qr"
    label = _as_text(
        data.get("ssid") or data.get("url") or data.get("phone") or data.get("query")
        or data.get("name") or data.get("text"),
        48,
    )
    stem = clean_filename(f"qr_{qr_type}_{label}".lower()) or f"qr_{qr_type}"
    filename = ensure_unique_filename(UPLOAD_FOLDER, f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    path = os.path.join(UPLOAD_FOLDER, filename)
    image.save(path, "PNG", optimize=True)
    generate_standard_renditions(filename, force=True)
    bump_media_revision()
    log_activity(username, "upload", filename=filename, details=f"qr-code:{qr_type}")
    return {
        "filename": filename,
        "preview_url": get_media_url(filename, context="campaign", generate_missing=True),
        "original_url": get_media_url(filename, context="preview", allow_original=True, generate_missing=True),
    }
