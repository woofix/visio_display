import contextlib
import math
import os
import unicodedata
from datetime import date, datetime, timezone, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont

from constants import UPLOAD_FOLDER, LAT, LNG, DEFAULT_METEO_VILLE, DEFAULT_METEO_TZ
from services.config_svc import load_config
from services.i18n import _t, get_language
from services.media_svc import strip_html
from translations import JOURS_BY_LANG, MOIS_BY_LANG, WMO_CODES_BY_LANG


def get_utc_offset():
    return 2 if 4 <= datetime.now().month <= 10 else 1


def _get_meteo_location(cfg):
    lat   = cfg.get("meteo_lat",   LAT)
    lng   = cfg.get("meteo_lng",   LNG)
    tz    = cfg.get("meteo_tz",    DEFAULT_METEO_TZ)
    ville = cfg.get("meteo_ville", DEFAULT_METEO_VILLE)
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        lat, lng = LAT, LNG
    return lat, lng, tz, ville


def _normalize_text(value):
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.casefold().strip()


def _normalize_school_zone(zone):
    normalized = _normalize_text(zone)
    aliases = {
        "a": "A",
        "zone a": "A",
        "b": "B",
        "zone b": "B",
        "c": "C",
        "zone c": "C",
        "corse": "Corse",
        "guadeloupe": "Guadeloupe",
        "guyane": "Guyane",
        "martinique": "Martinique",
        "mayotte": "Mayotte",
        "nouvelle caledonie": "Nouvelle Caledonie",
        "polynesie": "Polynesie",
        "reunion": "Reunion",
        "la reunion": "Reunion",
        "saint-pierre-et-miquelon": "Saint-Pierre-et-Miquelon",
        "saint pierre et miquelon": "Saint-Pierre-et-Miquelon",
        "wallis et futuna": "Wallis et Futuna",
    }
    return aliases.get(normalized)


def _guess_school_zone_from_city(city):
    city_name = _normalize_text(city)
    if not city_name:
        return "C"

    keyword_groups = {
        "A": (
            "besancon", "bordeaux", "clermont ferrand", "dijon", "grenoble",
            "limoges", "lyon", "poitiers",
        ),
        "B": (
            "aix marseille", "amiens", "caen", "lille", "nancy", "metz",
            "nantes", "nice", "normandie", "orleans", "reims", "rennes",
            "rouen", "strasbourg",
        ),
        "C": (
            "creteil", "montpellier", "paris", "toulouse", "versailles",
            "perpignan",
        ),
        "Corse": ("corse", "ajaccio", "bastia"),
        "Guadeloupe": ("guadeloupe", "basse terre", "pointe a pitre"),
        "Guyane": ("guyane", "cayenne"),
        "Martinique": ("martinique", "fort de france"),
        "Mayotte": ("mayotte", "mamoudzou"),
        "Nouvelle Caledonie": ("nouvelle caledonie", "noumea"),
        "Polynesie": ("polynesie", "papeete", "tahiti"),
        "Reunion": ("reunion", "saint denis"),
        "Saint-Pierre-et-Miquelon": ("saint-pierre-et-miquelon", "saint pierre"),
        "Wallis et Futuna": ("wallis", "futuna"),
    }
    for zone, keywords in keyword_groups.items():
        if any(keyword in city_name for keyword in keywords):
            return zone
    return "C"


def get_school_zone(cfg=None):
    if cfg is None:
        cfg = load_config()
    explicit_zone = _normalize_school_zone(cfg.get("school_zone"))
    if explicit_zone:
        return explicit_zone
    _lat, _lng, _tz, ville = _get_meteo_location(cfg)
    return _guess_school_zone_from_city(ville)


def _parse_api_date(raw_value):
    if not raw_value:
        return None
    raw_value = str(raw_value).strip()
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).date()
    except ValueError:
        with contextlib.suppress(ValueError):
            return date.fromisoformat(raw_value.split("T", 1)[0])
        with contextlib.suppress(ValueError):
            return datetime.strptime(raw_value[:8], "%Y%m%d").date()
    return None


def _holiday_date_label(day, lang):
    return day.strftime("%d/%m/%Y") if lang == "fr" else day.strftime("%Y-%m-%d")


def get_next_school_holiday(cfg=None):
    if cfg is None:
        cfg = load_config()
    lang = get_language()
    zone = get_school_zone(cfg)
    zone_label = f"Zone {zone}" if zone in {"A", "B", "C"} else zone
    normalized_zone_label = _normalize_text(zone_label)
    try:
        today = date.today()
        today_iso = today.isoformat()
        best = None
        endpoints = (
            (
                "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-calendrier-scolaire/records",
                {
                    "limit": 20,
                    "order_by": "start_date",
                    "where": (
                        f"start_date >= date'{today_iso}' "
                        f'AND zones like "%{zone_label}%" '
                        'AND population = "Élèves"'
                    ),
                },
            ),
            (
                "https://data.education.gouv.fr/api/records/1.0/search/",
                {
                    "dataset": "fr-en-calendrier-scolaire",
                    "rows": 20,
                    "sort": "start_date",
                    "refine.zones": zone_label,
                    "refine.population": "Élèves",
                    "q": today_iso,
                },
            ),
        )
        for url, params in endpoints:
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            payload = response.json()
            records = payload.get("results") or payload.get("records") or []
            for item in records:
                fields = item.get("fields", item)
                description = (fields.get("description") or "").strip()
                if not description:
                    continue
                description_norm = _normalize_text(description)
                if "vacances" not in description_norm and "pont" not in description_norm:
                    continue
                population = _normalize_text(fields.get("population"))
                if population and "eleves" not in population:
                    continue
                record_zone = _normalize_text(fields.get("zones"))
                if normalized_zone_label not in record_zone:
                    continue
                start_raw = fields.get("start_date") or fields.get("date_debut")
                end_raw = fields.get("end_date") or fields.get("date_fin")
                start_date = _parse_api_date(start_raw)
                end_date = _parse_api_date(end_raw)
                if not start_date or not end_date or start_date < today:
                    continue
                candidate = {
                    "delta": (start_date - today).days,
                    "label": description.upper(),
                    "sub_label": _t(
                        "ephemeris_school_break_dates",
                        lang,
                        start=_holiday_date_label(start_date, lang),
                        end=_holiday_date_label(end_date, lang),
                    ),
                }
                if best is None or candidate["delta"] < best["delta"]:
                    best = candidate
            if best is not None:
                return best

        ics_url_map = {
            "A": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Zone-A.ics",
            "B": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Zone-B.ics",
            "C": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Zone-C.ics",
            "Corse": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Corse.ics",
            "Guadeloupe": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Guadeloupe.ics",
            "Guyane": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Guyane.ics",
            "Martinique": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Martinique.ics",
            "Mayotte": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Mayotte.ics",
            "Nouvelle Caledonie": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/NouvelleCaledonie.ics",
            "Polynesie": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Polynesie.ics",
            "Reunion": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Reunion.ics",
            "Saint-Pierre-et-Miquelon": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/SaintPierreEtMiquelon.ics",
            "Wallis et Futuna": "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/WallisEtFutuna.ics",
        }
        ics_url = ics_url_map.get(zone)
        if not ics_url:
            return None
        response = requests.get(ics_url, timeout=5)
        response.raise_for_status()
        blocks = response.text.split("BEGIN:VEVENT")
        for block in blocks[1:]:
            summary = ""
            start_date = None
            end_date = None
            for raw_line in block.splitlines():
                line = raw_line.strip()
                if line.startswith("SUMMARY:"):
                    summary = line.split(":", 1)[1].strip()
                elif line.startswith("DTSTART"):
                    start_date = _parse_api_date(line.split(":", 1)[1].strip())
                elif line.startswith("DTEND"):
                    end_date = _parse_api_date(line.split(":", 1)[1].strip())
            if not summary or not start_date or start_date < today:
                continue
            if "vacances" not in _normalize_text(summary) and "pont" not in _normalize_text(summary):
                continue
            if end_date and end_date > start_date:
                end_date = end_date - timedelta(days=1)
            candidate = {
                "delta": (start_date - today).days,
                "label": summary.upper(),
                "sub_label": _t(
                    "ephemeris_school_break_dates",
                    lang,
                    start=_holiday_date_label(start_date, lang),
                    end=_holiday_date_label(end_date or start_date, lang),
                ),
            }
            if best is None or candidate["delta"] < best["delta"]:
                best = candidate
        return best
    except Exception as e:
        print("[SCHOOL HOLIDAYS ERROR]", e)
    return None


def _fit_font(draw, text, max_width, font_path, start_size, min_size=20):
    size = start_size
    try:
        font = ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()
    while size > min_size and draw.textlength(text, font=font) > max_width:
        size -= 2
        with contextlib.suppress(Exception):
            font = ImageFont.truetype(font_path, size)
    return font


def get_ephemeride_slot():
    now  = datetime.now()
    slot = (now.hour // 2) * 2
    return now.strftime(f"%Y-%m-%d_{slot:02d}h")


def get_ephemeride_nominis():
    url = "https://nominis.cef.fr/json/saintdujour.php"
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data  = r.json()
        saint = data["response"]["saintdujour"]
        nom   = strip_html(saint.get("nom", "Ephemeride"))
        desc  = strip_html(saint.get("description", ""))
        return nom, desc
    except Exception as e:
        print("[NOMINIS ERROR]", e)
        lang = get_language()
        return _t('ephemeris_saint_default', lang), ""


def get_sun_times(cfg=None):
    if cfg is None:
        cfg = load_config()
    lat, lng, _tz, _ville = _get_meteo_location(cfg)
    try:
        r = requests.get(
            "https://api.sunrise-sunset.org/json",
            params={"lat": lat, "lng": lng, "formatted": 0},
            timeout=5
        )
        r.raise_for_status()
        data    = r.json()["results"]
        tz      = timezone(timedelta(hours=get_utc_offset()))
        lever   = datetime.fromisoformat(data["sunrise"]).astimezone(tz).strftime("%H:%M")
        coucher = datetime.fromisoformat(data["sunset"]).astimezone(tz).strftime("%H:%M")
        return lever, coucher
    except Exception as e:
        print("[SUN ERROR]", e)
        return "--:--", "--:--"


def get_weather_palette(code):
    if code == 0:
        return (230, 140, 40),  (80,  160, 240), (0.9, 0.55, 0.0)
    elif code == 1:
        return (210, 150, 60),  (100, 160, 230), (0.8, 0.50, 0.1)
    elif code == 2:
        return (140, 155, 185), (90,  115, 160), (0.35, 0.40, 0.60)
    elif code == 3:
        return (85,  90,  110), (50,  55,  75),  (0.28, 0.30, 0.40)
    elif code in (45, 48):
        return (155, 160, 170), (110, 115, 130), (0.50, 0.52, 0.58)
    elif code in (51, 53, 55):
        return (75,  105, 145), (40,  70,  110), (0.18, 0.32, 0.55)
    elif code in (61, 63, 65):
        return (30,  60,  115), (10,  35,  80),  (0.08, 0.18, 0.50)
    elif code in (71, 73, 75):
        return (175, 195, 225), (130, 155, 195), (0.55, 0.65, 0.85)
    elif code in (80, 81, 82):
        return (40,  70,  125), (15,  40,  90),  (0.12, 0.22, 0.55)
    elif code in (95, 96, 99):
        return (40,  25,  70),  (15,  8,   45),  (0.50, 0.08, 0.80)
    else:
        return (94,  62,  139), (146, 115, 198), (0.00, 0.00, 0.50)


def get_meteo(cfg=None):
    if cfg is None:
        cfg = load_config()
    lat, lng, tz_name, _ville = _get_meteo_location(cfg)
    lang = get_language()
    wmo  = WMO_CODES_BY_LANG.get(lang, WMO_CODES_BY_LANG['fr'])
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lng,
                "current": "temperature_2m,apparent_temperature,weathercode,windspeed_10m,precipitation",
                "wind_speed_unit": "kmh", "timezone": tz_name
            },
            timeout=5
        )
        r.raise_for_status()
        current   = r.json()["current"]
        temp      = current.get("temperature_2m", "--")
        temp_res  = current.get("apparent_temperature", "--")
        code      = current.get("weathercode", 0)
        vent      = current.get("windspeed_10m", "--")
        precip    = current.get("precipitation", 0)
        condition = wmo.get(code, _t('ephemeris_weather_unknown', lang))
        return {
            "temp":      f"{temp:.0f}°C",
            "ressenti":  f"{temp_res:.0f}°C",
            "condition": condition.upper(),
            "vent":      f"{vent:.0f} km/h",
            "precip":    f"{precip:.1f} mm",
            "code":      code,
        }
    except Exception as e:
        print("[METEO ERROR]", e)
        return {"temp": "--°C", "ressenti": "--°C",
                "condition": _t('ephemeris_weather_unknown', lang).upper(),
                "vent": "-- km/h", "precip": "-- mm", "code": -1}


def draw_weather_icon(draw, cx, cy, code, size=150):
    r = size // 2

    def sun(x, y, sun_r, rays=8):
        draw.ellipse([x-sun_r, y-sun_r, x+sun_r, y+sun_r], fill=(255, 220, 50))
        ray_len = sun_r * 0.65
        ray_w   = max(3, size // 35)
        for i in range(rays):
            angle = math.radians(i * 360 / rays)
            x1 = x + math.cos(angle) * (sun_r + 6)
            y1 = y + math.sin(angle) * (sun_r + 6)
            x2 = x + math.cos(angle) * (sun_r + 6 + ray_len)
            y2 = y + math.sin(angle) * (sun_r + 6 + ray_len)
            draw.line([(x1, y1), (x2, y2)], fill=(255, 210, 40), width=ray_w)

    def cloud(x, y, cs, color=(215, 220, 240)):
        draw.ellipse([x-cs*.5, y-cs*.35, x+cs*.5, y+cs*.45], fill=color)
        draw.ellipse([x-cs*.75, y-cs*.1,  x+cs*.0, y+cs*.45], fill=color)
        draw.ellipse([x+cs*.0,  y-cs*.1,  x+cs*.75,y+cs*.45], fill=color)
        draw.ellipse([x-cs*.3,  y-cs*.55, x+cs*.3, y+cs*.05], fill=color)
        draw.rectangle([int(x-cs*.75), int(y+cs*.15), int(x+cs*.75), int(y+cs*.45)], fill=color)

    def rain_drops(base_x, base_y, num, spread, drop_len, color=(100, 165, 230)):
        w = max(2, size // 40)
        for i in range(num):
            dx = int(base_x - spread/2 + i * spread / max(num-1, 1))
            dy = base_y + (i % 3) * (size // 18)
            draw.line([(dx, dy), (dx - drop_len//4, dy + drop_len)], fill=color, width=w)

    def snow_flakes(base_x, base_y, num, spread, flake_r, color=(195, 225, 255)):
        w = max(2, size // 40)
        for i in range(num):
            px = int(base_x - spread/2 + i * spread / max(num-1, 1))
            py = base_y + (i % 2) * (size // 14)
            for angle in [0, 60, 120]:
                rad = math.radians(angle)
                draw.line([
                    (px - int(math.cos(rad)*flake_r), py - int(math.sin(rad)*flake_r)),
                    (px + int(math.cos(rad)*flake_r), py + int(math.sin(rad)*flake_r))
                ], fill=color, width=w)

    def lightning(x, y, bh, color=(255, 240, 30)):
        bw = bh * 0.42
        pts = [
            (x + bw*.2,  y),
            (x - bw*.1,  y + bh*.44),
            (x + bw*.28, y + bh*.44),
            (x - bw*.2,  y + bh),
            (x + bw*.5,  y + bh*.52),
            (x + bw*.08, y + bh*.52),
        ]
        draw.polygon([(int(px), int(py)) for px, py in pts], fill=color)

    def fog_lines(x, y, width, num, color=(165, 175, 200)):
        lh = max(4, size // 22)
        gap = size // (num + 1)
        for i in range(num):
            lw = int(width * (0.55 + 0.45 * (1 - abs(i - num//2) / (num//2 + 1))))
            lx = x - lw // 2
            ly = y + i * gap
            draw.rounded_rectangle([lx, ly, lx+lw, ly+lh], radius=lh//2, fill=color)

    if code == 0:
        sun(cx, cy, int(r * 0.55))
    elif code in (1, 2):
        sun(cx - r//5, cy - r//5, int(r * 0.38))
        cloud(cx + r//8, cy + r//7, int(r * 0.65))
    elif code == 3:
        cloud(cx, cy, int(r * 0.85), color=(155, 160, 178))
    elif code in (45, 48):
        fog_lines(cx, int(cy - r*.25), int(r*1.7), 5)
    elif code in (51, 53, 55):
        cloud(cx, int(cy - r*.12), int(r*.75), color=(175, 180, 200))
        rain_drops(cx, int(cy + r*.52), 3, int(r*.9), int(r*.45), color=(140, 185, 225))
    elif code in (61, 63, 65):
        cloud(cx, int(cy - r*.12), int(r*.75), color=(135, 140, 162))
        rain_drops(cx, int(cy + r*.52), 5, int(r*.95), int(r*.55), color=(90, 155, 220))
    elif code in (71, 73, 75):
        cloud(cx, int(cy - r*.12), int(r*.75), color=(195, 200, 220))
        snow_flakes(cx, int(cy + r*.58), 4, int(r*.9), int(r*.22))
    elif code in (80, 81, 82):
        cloud(cx, int(cy - r*.12), int(r*.75), color=(115, 120, 142))
        rain_drops(cx, int(cy + r*.48), 6, int(r*1.1), int(r*.65), color=(75, 140, 210))
    elif code in (95, 96, 99):
        cloud(cx, int(cy - r*.22), int(r*.75), color=(78, 82, 100))
        lightning(cx - r//9, int(cy + r*.18), int(r*.82))
        if code in (96, 99):
            hr = max(5, size // 22)
            for hx, hy in [(cx - r//3, int(cy + r*.88)), (cx + r//4, int(cy + r*.78))]:
                draw.ellipse([hx-hr, hy-hr, hx+hr, hy+hr], fill=(195, 225, 255))
    else:
        cloud(cx, cy, int(r * 0.75), color=(155, 160, 178))


def generate_ephemeride_image(force=False):
    lang  = get_language()
    JOURS = JOURS_BY_LANG.get(lang, JOURS_BY_LANG['fr'])
    MOIS  = MOIS_BY_LANG.get(lang, MOIS_BY_LANG['fr'])

    slot     = get_ephemeride_slot()
    filename = f"ephemeride_{slot}.jpg"
    path     = os.path.join(UPLOAD_FOLDER, filename)

    for f in os.listdir(UPLOAD_FOLDER):
        if f.startswith("ephemeride_") and f != filename:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(UPLOAD_FOLDER, f))

    if os.path.exists(path) and not force:
        return

    cfg              = load_config()
    nom, description = get_ephemeride_nominis()
    lever, coucher   = get_sun_times(cfg)
    meteo            = get_meteo(cfg)
    school_holiday   = get_next_school_holiday(cfg)
    today            = date.today()
    date_str         = f"{JOURS[today.weekday()]} {today.day} {MOIS[today.month]} {today.year}"

    img  = Image.new("RGB", (1920, 1080), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    top, bot, halo_rgb = get_weather_palette(meteo.get("code", -1))
    for y in range(1080):
        t = y / 1080
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (1920, y)], fill=(r, g, b))

    halo      = Image.new("RGB", (1920, 1080), (0, 0, 0))
    halo_draw = ImageDraw.Draw(halo)
    for radius in range(350, 0, -8):
        intensity = int(90 * (1 - radius / 350))
        hr = min(255, int(intensity * halo_rgb[0] * 2))
        hg = min(255, int(intensity * halo_rgb[1] * 2))
        hb = min(255, int(intensity * halo_rgb[2] * 2))
        halo_draw.ellipse(
            [960 - radius, 540 - radius, 960 + radius, 540 + radius],
            outline=(hr, hg, hb)
        )
    img  = Image.blend(img, halo, alpha=0.5)
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        font_date  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      50)
        font_saint = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 75)
        font_desc  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      42)
        font_sun   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      36)
        font_meteo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_mlab  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      34)
    except Exception:
        default = ImageFont.load_default()
        font_title = font_date = font_saint = font_desc = default
        font_sun = font_label = font_meteo = font_mlab = default

    draw.rectangle([160, 195, 1760, 200], fill=(200, 180, 255))
    draw.text((960, 155), _t('ephemeris_title', lang),    fill=(220, 200, 255), font=font_title, anchor="mm")
    draw.text((960, 290), date_str,                        fill=(255, 255, 255), font=font_date,  anchor="mm")
    draw.rectangle([160, 370, 1760, 374], fill=(200, 180, 255))
    draw.text((960, 450), nom.upper(),                     fill=(255, 255, 255), font=font_saint, anchor="mm")

    if description:
        words = description.split()
        lines, line = [], ""
        for word in words:
            test = f"{line} {word}".strip()
            if len(test) > 72:
                lines.append(line)
                line = word
            else:
                line = test
        if line:
            lines.append(line)
        y_desc = 540
        for line_text in lines[:2]:
            draw.text((960, y_desc), line_text, fill=(210, 190, 255), font=font_desc, anchor="mm")
            y_desc += 58

    draw.rectangle([160, 650, 1760, 654], fill=(200, 180, 255))
    draw_weather_icon(draw, 255, 762, meteo["code"], size=130)

    temp_label = _t('ephemeris_temp_label', lang)
    feel_label = _t('ephemeris_feel_label', lang)
    wind_label = _t('ephemeris_wind_label', lang)
    rain_label = _t('ephemeris_rain_label', lang)

    _lat, _lng, _tz, ville = _get_meteo_location(cfg)
    meteo_label = f"{_t('ephemeris_meteo_prefix', lang)} - {ville.upper()}"
    draw.text((640,  682), meteo_label,                                                           fill=(200, 180, 255), font=font_mlab,  anchor="mm")

    condition_text = meteo["condition"]
    _font_meteo = font_meteo
    _meteo_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    _meteo_size = 48
    while _meteo_size > 20 and draw.textlength(condition_text, font=_font_meteo) > 560:
        _meteo_size -= 2
        try:
            _font_meteo = ImageFont.truetype(_meteo_font_path, _meteo_size)
        except Exception:
            break
    draw.text((640,  730), condition_text,                                                         fill=(255, 255, 255), font=_font_meteo, anchor="mm")
    draw.text((640,  778), f"{temp_label} : {meteo['temp']}  ({feel_label} {meteo['ressenti']})", fill=(200, 230, 255), font=font_mlab,  anchor="mm")
    draw.text((640,  820), f"{wind_label} : {meteo['vent']}   {rain_label} : {meteo['precip']}",  fill=(200, 230, 255), font=font_mlab,  anchor="mm")
    draw.rectangle([930, 665, 934, 855], fill=(200, 180, 255))
    draw.text((1340, 700), _t('ephemeris_sun_label', lang),    fill=(200, 180, 255), font=font_mlab,  anchor="mm")
    draw.text((1200, 760), _t('ephemeris_sunrise', lang),      fill=(200, 180, 255), font=font_label, anchor="mm")
    draw.text((1200, 808), lever,                               fill=(255, 230, 150), font=font_sun,   anchor="mm")
    draw.text((1480, 760), _t('ephemeris_sunset', lang),       fill=(200, 180, 255), font=font_label, anchor="mm")
    draw.text((1480, 808), coucher,                             fill=(255, 180, 100), font=font_sun,   anchor="mm")
    draw.rectangle([160, 870, 1760, 874], fill=(200, 180, 255))

    events = cfg.get("events", [])
    upcoming = []
    if school_holiday:
        upcoming.append(school_holiday)
    for ev in events:
        try:
            ev_date = date.fromisoformat(ev["date"])
            delta   = (ev_date - today).days
            if delta >= 0:
                upcoming.append({"delta": delta, "label": ev["label"].upper(), "sub_label": None})
        except (ValueError, KeyError):
            pass
    upcoming.sort(key=lambda item: (item["delta"], item["label"]))

    if upcoming:
        try:
            font_cd_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
            font_cd_lbl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      34)
            font_cd_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      24)
        except Exception:
            font_cd_num = font_cd_lbl = font_cd_sub = ImageFont.load_default()

        to_show    = upcoming[:2]
        y_num      = 948
        y_lbl      = 998
        y_sub      = 1038
        today_text = _t('ephemeris_today', lang)
        if len(to_show) == 1:
            item = to_show[0]
            delta = item["delta"]
            label = item["label"]
            sub_label = item.get("sub_label")
            j_text = today_text if delta == 0 else f"J-{delta}"
            draw.text((960, y_num), j_text,       fill=(255, 220, 100), font=font_cd_num, anchor="mm")
            label_font = _fit_font(
                draw, label, 1040,
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34, min_size=22
            )
            draw.text((960, y_lbl), label, fill=(210, 190, 255), font=label_font, anchor="mm")
            if sub_label:
                sub_font = _fit_font(
                    draw, sub_label, 1040,
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24, min_size=18
                )
                draw.text((960, y_sub), sub_label, fill=(200, 230, 255), font=sub_font, anchor="mm")
        else:
            draw.rectangle([930, 895, 934, 1055], fill=(200, 180, 255))
            for i, item in enumerate(to_show):
                delta = item["delta"]
                label = item["label"]
                sub_label = item.get("sub_label")
                cx     = 480 if i == 0 else 1440
                j_text = today_text if delta == 0 else f"J-{delta}"
                draw.text((cx, y_num), j_text,       fill=(255, 220, 100), font=font_cd_num, anchor="mm")
                label_font = _fit_font(
                    draw, label, 760,
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32, min_size=20
                )
                draw.text((cx, y_lbl), label, fill=(210, 190, 255), font=label_font, anchor="mm")
                if sub_label:
                    sub_font = _fit_font(
                        draw, sub_label, 760,
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22, min_size=16
                    )
                    draw.text((cx, y_sub), sub_label, fill=(200, 230, 255), font=sub_font, anchor="mm")

    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        img.save(tmp_path, "JPEG", quality=95)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
