import contextlib
import math
import os
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
    for ev in events:
        try:
            ev_date = date.fromisoformat(ev["date"])
            delta   = (ev_date - today).days
            if delta >= 0:
                upcoming.append((delta, ev["label"]))
        except (ValueError, KeyError):
            pass
    upcoming.sort()

    if upcoming:
        try:
            font_cd_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
            font_cd_lbl = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      34)
        except Exception:
            font_cd_num = font_cd_lbl = ImageFont.load_default()

        to_show    = upcoming[:2]
        y_num      = 960
        y_lbl      = 1020
        today_text = _t('ephemeris_today', lang)
        if len(to_show) == 1:
            delta, label = to_show[0]
            j_text = today_text if delta == 0 else f"J-{delta}"
            draw.text((960, y_num), j_text,       fill=(255, 220, 100), font=font_cd_num, anchor="mm")
            draw.text((960, y_lbl), label.upper(), fill=(210, 190, 255), font=font_cd_lbl, anchor="mm")
        else:
            draw.rectangle([930, 895, 934, 1055], fill=(200, 180, 255))
            for i, (delta, label) in enumerate(to_show):
                cx     = 480 if i == 0 else 1440
                j_text = today_text if delta == 0 else f"J-{delta}"
                draw.text((cx, y_num), j_text,       fill=(255, 220, 100), font=font_cd_num, anchor="mm")
                draw.text((cx, y_lbl), label.upper(), fill=(210, 190, 255), font=font_cd_lbl, anchor="mm")

    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        img.save(tmp_path, "JPEG", quality=95)
        os.replace(tmp_path, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise
