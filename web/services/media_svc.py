import html
import json
import os
import re
import subprocess
from datetime import date, datetime, time as dtime

from PIL import Image
from unidecode import unidecode

from constants import (
    UPLOAD_FOLDER, IMAGES_FOLDER, DEFAULT_LOGO,
    IMAGE_EXTS, VIDEO_EXTS, MEDIA_EXTS,
)
from services.config_svc import load_config


def strip_html(text):
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    return text


def clean_filename(filename):
    filename = unidecode(filename)
    filename = filename.replace(' ', '_')
    filename = ''.join(c for c in filename if c.isalnum() or c in ('_', '.', '-'))
    return filename


def get_all_media():
    cfg   = load_config()
    files = [f for f in os.listdir(UPLOAD_FOLDER)
             if f.lower().endswith(MEDIA_EXTS)]
    order     = cfg.get("order", [])
    ordered   = [f for f in order if f in files]
    unordered = [f for f in files if f not in ordered]
    return ordered + unordered


def is_media_scheduled(filename, cfg):
    schedules = cfg.get("schedules", {})
    if filename not in schedules:
        return True
    sched = schedules[filename]
    now   = datetime.now()
    today = now.date()

    date_start = sched.get("date_start")
    date_end   = sched.get("date_end")
    if date_start:
        try:
            if today < date.fromisoformat(date_start):
                return False
        except ValueError:
            pass
    if date_end:
        try:
            if today > date.fromisoformat(date_end):
                return False
        except ValueError:
            pass

    time_start = sched.get("time_start")
    time_end   = sched.get("time_end")
    if time_start or time_end:
        current = now.time().replace(second=0, microsecond=0)
        if time_start:
            try:
                h, m = map(int, time_start.split(":"))
                if current < dtime(h, m):
                    return False
            except (ValueError, AttributeError):
                pass
        if time_end:
            try:
                h, m = map(int, time_end.split(":"))
                if current > dtime(h, m):
                    return False
            except (ValueError, AttributeError):
                pass

    return True


def get_logo_path():
    cfg  = load_config()
    logo = cfg.get('logo', DEFAULT_LOGO)
    if not os.path.exists(os.path.join(IMAGES_FOLDER, logo)):
        logo = DEFAULT_LOGO
    return f'/static/images/{logo}'


def get_disk_usage():
    import shutil
    total, used, free = shutil.disk_usage(UPLOAD_FOLDER)
    return {
        "total": round(total / (1024**3), 1),
        "used":  round(used  / (1024**3), 1),
        "free":  round(free  / (1024**3), 1),
    }


def get_file_info(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return {"size": "--", "dims": "--", "type": "unknown"}
    size = os.path.getsize(path)
    ext  = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        try:
            with Image.open(path) as img:
                w, h = img.size
        except Exception:
            w, h = 0, 0
        return {"size": f"{round(size/1024)} Ko", "dims": f"{w}x{h}", "type": "image"}
    elif ext in VIDEO_EXTS:
        return {"size": f"{round(size/1024/1024, 1)} Mo", "dims": "video", "type": "video"}
    return {"size": f"{round(size/1024)} Ko", "dims": "--", "type": "unknown"}


def is_h264_mp4(path):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', path
        ], capture_output=True, check=True)
        info = json.loads(result.stdout)
        for stream in info.get('streams', []):
            if stream.get('codec_type') == 'video':
                return stream.get('codec_name') == 'h264'
        return False
    except Exception:
        return False


def _get_video_duration_ms(path):
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', path
        ], capture_output=True, text=True, check=True)
        info     = json.loads(result.stdout)
        duration = float(info.get('format', {}).get('duration', 0))
        return int(duration * 1000)
    except Exception:
        return 0


def valid_screen_name(name):
    from constants import RESERVED_SCREEN_NAMES
    return bool(name and re.match(r'^[a-z0-9_-]{1,32}$', name)
                and name not in RESERVED_SCREEN_NAMES)
