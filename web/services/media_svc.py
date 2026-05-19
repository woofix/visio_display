# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import html
import json
import os
import re
import subprocess
import threading
import time
from datetime import date, datetime, time as dtime

from PIL import Image, ImageOps
from unidecode import unidecode

from constants import (
    UPLOAD_FOLDER, VIDEO_THUMB_FOLDER, IMAGE_VARIANT_FOLDER, VIDEO_VARIANT_FOLDER, VIDEO_POSTER_FOLDER,
    IMAGES_FOLDER, DEFAULT_LOGO,
    IMAGE_EXTS, VIDEO_EXTS, MEDIA_EXTS, ORIGINAL_MEDIA_URL,
)
from services.config_svc import load_config
from services.playlist_cache_svc import make_media_revision

THUMB_SIZE = (480, 270)
MAX_VARIANT_WIDTH = 3840
MAX_VARIANT_HEIGHT = 3840
IMAGE_RENDITION_PROFILES = {
    'thumb': {'max_width': 320, 'max_height': 320, 'quality': 82},
    'small': {'max_width': 640, 'max_height': 640, 'quality': 84},
    'medium': {'max_width': 1280, 'max_height': 1280, 'quality': 85},
    'large': {'max_width': 1920, 'max_height': 1920, 'quality': 86},
    'xlarge': {'max_width': 2560, 'max_height': 2560, 'quality': 88},
}
VIDEO_POSTER_PROFILES = {
    'thumb': {'width': 320, 'height': 180},
    'small': {'width': 640, 'height': 360},
    'medium': {'width': 1280, 'height': 720},
    'large': {'width': 1920, 'height': 1080},
}
VIDEO_RENDITION_PROFILES = {
    'v720': {'width': 1280, 'height': 720, 'video_bitrate': '2500k', 'audio_bitrate': '128k'},
    'v1080': {'width': 1920, 'height': 1080, 'video_bitrate': '5000k', 'audio_bitrate': '160k'},
    'v1440': {'width': 2560, 'height': 1440, 'video_bitrate': '9000k', 'audio_bitrate': '192k'},
    'v2160': {'width': 3840, 'height': 2160, 'video_bitrate': '16000k', 'audio_bitrate': '192k'},
}
DISPLAY_VIDEO_PROFILES = ('v1080', 'v2160')
DEFAULT_CONTEXTS = {
    'admin': {'image_profile': 'thumb', 'video_poster_profile': 'thumb', 'video_profile': 'v720'},
    'campaign': {'image_profile': 'small', 'video_poster_profile': 'small', 'video_profile': 'v720'},
    'preview': {'image_profile': 'medium', 'video_poster_profile': 'medium', 'video_profile': 'v1080'},
    'display': {'image_profile': 'large', 'video_poster_profile': 'large', 'video_profile': 'v1080'},
}
_ALL_MEDIA_CACHE = {}
_ALL_MEDIA_CACHE_MAX_ENTRIES = 32
_ALL_MEDIA_CACHE_LOCK = threading.Lock()
_MEDIA_METADATA_CACHE = {}
_MEDIA_METADATA_CACHE_MAX_ENTRIES = 512
_MEDIA_METADATA_CACHE_LOCK = threading.Lock()
_DISK_USAGE_CACHE = None
_DISK_USAGE_CACHE_EXPIRES_AT = 0.0
_DISK_USAGE_CACHE_TTL_SECONDS = 10
_DISK_USAGE_CACHE_LOCK = threading.Lock()


def strip_html(text):
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    return text


def clean_filename(filename):
    filename = unidecode(filename)
    filename = filename.replace(' ', '_')
    filename = ''.join(c for c in filename if c.isalnum() or c in ('_', '.', '-'))
    return filename


def ensure_unique_filename(directory, filename):
    base, ext = os.path.splitext(filename)
    candidate = filename
    index = 1
    while os.path.exists(os.path.join(directory, candidate)):
        candidate = f"{base}_{index}{ext}"
        index += 1
    return candidate


def is_valid_uploaded_image(path):
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def get_media_type(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in VIDEO_EXTS:
        return 'video'
    return 'unknown'


def get_image_profile_names():
    return list(IMAGE_RENDITION_PROFILES.keys())


def get_video_poster_profile_names():
    return list(VIDEO_POSTER_PROFILES.keys())


def get_video_profile_names():
    return list(VIDEO_RENDITION_PROFILES.keys())


def get_thumbnail_name(filename):
    stem, ext = os.path.splitext(os.path.basename(filename))
    suffix = ext[1:].lower() if ext else 'file'
    return f'{stem}__{suffix}.jpg'


def _normalize_variant_bounds(width, height):
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    width = max(320, min(width, MAX_VARIANT_WIDTH))
    height = max(180, min(height, MAX_VARIANT_HEIGHT))
    return width, height


def _normalize_dimension(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def get_image_variant_name(filename, width, height):
    stem, ext = os.path.splitext(os.path.basename(filename))
    suffix = ext[1:].lower() if ext else 'file'
    return f'{stem}__{suffix}__{width}x{height}.jpg'


def get_image_rendition_name(filename, profile_name):
    stem, ext = os.path.splitext(os.path.basename(filename))
    suffix = ext[1:].lower() if ext else 'file'
    return f'{stem}__{suffix}__{profile_name}.jpg'


def get_image_variant_path(filename, width, height):
    return os.path.join(IMAGE_VARIANT_FOLDER, get_image_variant_name(filename, width, height))


def get_image_rendition_path(filename, profile_name):
    return os.path.join(IMAGE_VARIANT_FOLDER, get_image_rendition_name(filename, profile_name))


def _url_for_existing_path(pathname, url_prefix, filename):
    if os.path.exists(pathname):
        cache_bust = int(os.path.getmtime(pathname))
        return f'{url_prefix}/{filename}?v={cache_bust}'
    return None


def get_original_media_url(filename):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    cache_bust = int(os.path.getmtime(source_path))
    return f'{ORIGINAL_MEDIA_URL}/{filename}?v={cache_bust}'


def get_image_variant_url(filename, width, height):
    rendition_name = get_image_variant_name(filename, width, height)
    return _url_for_existing_path(
        get_image_variant_path(filename, width, height),
        '/static/data/variants',
        rendition_name,
    )


def get_image_rendition_url(filename, profile_name):
    rendition_name = get_image_rendition_name(filename, profile_name)
    return _url_for_existing_path(
        get_image_rendition_path(filename, profile_name),
        '/static/data/variants',
        rendition_name,
    )


def get_existing_image_rendition_url(filename, profile_name):
    return get_image_rendition_url(filename, profile_name)


def get_thumbnail_path(filename):
    return os.path.join(VIDEO_THUMB_FOLDER, get_thumbnail_name(filename))


def get_thumbnail_url(filename):
    thumb_name = get_thumbnail_name(filename)
    return _url_for_existing_path(
        get_thumbnail_path(filename),
        '/static/data/thumbnails',
        thumb_name,
    )


def get_existing_thumbnail_url(filename):
    return get_thumbnail_url(filename)


def get_video_poster_name(filename, profile_name):
    stem, ext = os.path.splitext(os.path.basename(filename))
    suffix = ext[1:].lower() if ext else 'file'
    return f'{stem}__{suffix}__{profile_name}.jpg'


def get_video_poster_path(filename, profile_name):
    return os.path.join(VIDEO_POSTER_FOLDER, get_video_poster_name(filename, profile_name))


def get_video_poster_url(filename, profile_name):
    poster_name = get_video_poster_name(filename, profile_name)
    return _url_for_existing_path(
        get_video_poster_path(filename, profile_name),
        '/static/data/video_posters',
        poster_name,
    )


def get_existing_video_poster_url(filename, profile_name):
    return get_video_poster_url(filename, profile_name)


def get_video_variant_name(filename, profile_name):
    stem, _ext = os.path.splitext(os.path.basename(filename))
    return f'{stem}__{profile_name}.mp4'


def get_video_variant_path(filename, profile_name):
    return os.path.join(VIDEO_VARIANT_FOLDER, get_video_variant_name(filename, profile_name))


def get_video_variant_url(filename, profile_name):
    variant_name = get_video_variant_name(filename, profile_name)
    return _url_for_existing_path(
        get_video_variant_path(filename, profile_name),
        '/static/data/video_variants',
        variant_name,
    )


def get_existing_video_variant_url(filename, profile_name):
    return get_video_variant_url(filename, profile_name)


def delete_media_thumbnail(filename):
    thumb_path = get_thumbnail_path(filename)
    if os.path.exists(thumb_path):
        try:
            os.remove(thumb_path)
        except OSError:
            pass


def delete_image_variants(filename):
    stem, ext = os.path.splitext(os.path.basename(filename))
    suffix = ext[1:].lower() if ext else 'file'
    prefix = f'{stem}__{suffix}__'
    if not os.path.isdir(IMAGE_VARIANT_FOLDER):
        return
    for entry in os.listdir(IMAGE_VARIANT_FOLDER):
        if entry.startswith(prefix):
            try:
                os.remove(os.path.join(IMAGE_VARIANT_FOLDER, entry))
            except OSError:
                pass


def delete_video_variants(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    prefixes = [f'{stem}__']
    for folder in (VIDEO_VARIANT_FOLDER, VIDEO_POSTER_FOLDER):
        if not os.path.isdir(folder):
            continue
        for entry in os.listdir(folder):
            if not any(entry.startswith(prefix) for prefix in prefixes):
                continue
            try:
                os.remove(os.path.join(folder, entry))
            except OSError:
                pass


def _fit_and_pad_thumbnail(img):
    frame = ImageOps.exif_transpose(img).convert('RGB')
    frame.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', THUMB_SIZE, 'black')
    offset = ((THUMB_SIZE[0] - frame.width) // 2, (THUMB_SIZE[1] - frame.height) // 2)
    canvas.paste(frame, offset)
    return canvas


def _thumbnail_to_fit(img, width, height):
    frame = ImageOps.exif_transpose(img).convert('RGB')
    frame.thumbnail((width, height), Image.Resampling.LANCZOS)
    return frame


def generate_image_thumbnail(source_path, filename):
    os.makedirs(VIDEO_THUMB_FOLDER, exist_ok=True)
    thumb_path = get_thumbnail_path(filename)
    try:
        with Image.open(source_path) as img:
            _fit_and_pad_thumbnail(img).save(thumb_path, 'JPEG', quality=82, optimize=True)
        return thumb_path
    except Exception:
        return None


def generate_image_rendition(source_path, filename, profile_name):
    profile = IMAGE_RENDITION_PROFILES.get(profile_name)
    if not profile:
        return None
    os.makedirs(IMAGE_VARIANT_FOLDER, exist_ok=True)
    rendition_path = get_image_rendition_path(filename, profile_name)
    try:
        with Image.open(source_path) as img:
            frame = _thumbnail_to_fit(img, profile['max_width'], profile['max_height'])
            frame.save(
                rendition_path,
                'JPEG',
                quality=profile.get('quality', 86),
                optimize=True,
            )
        return rendition_path
    except Exception:
        return None


def generate_image_variant(source_path, filename, width, height):
    bounds = _normalize_variant_bounds(width, height)
    if not bounds:
        return None
    width, height = bounds
    os.makedirs(IMAGE_VARIANT_FOLDER, exist_ok=True)
    variant_path = get_image_variant_path(filename, width, height)
    try:
        with Image.open(source_path) as img:
            frame = ImageOps.exif_transpose(img).convert('RGB')
            frame.thumbnail((width, height), Image.Resampling.LANCZOS)
            frame.save(variant_path, 'JPEG', quality=86, optimize=True)
        return variant_path
    except Exception:
        return None


def generate_video_thumbnail(source_path, filename):
    os.makedirs(VIDEO_THUMB_FOLDER, exist_ok=True)
    thumb_path = get_thumbnail_path(filename)
    try:
        subprocess.run([
            'ffmpeg', '-y',
            '-i', source_path,
            '-vf', 'thumbnail,scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2:black',
            '-frames:v', '1',
            '-q:v', '5',
            thumb_path,
        ], capture_output=True, check=True)
        return thumb_path
    except Exception:
        return None


def generate_video_poster(source_path, filename, profile_name):
    profile = VIDEO_POSTER_PROFILES.get(profile_name)
    if not profile:
        return None
    os.makedirs(VIDEO_POSTER_FOLDER, exist_ok=True)
    poster_path = get_video_poster_path(filename, profile_name)
    filter_expr = (
        'thumbnail,'
        f'scale={profile["width"]}:{profile["height"]}:force_original_aspect_ratio=decrease,'
        f'pad={profile["width"]}:{profile["height"]}:(ow-iw)/2:(oh-ih)/2:black'
    )
    try:
        subprocess.run([
            'ffmpeg', '-y',
            '-i', source_path,
            '-vf', filter_expr,
            '-frames:v', '1',
            '-q:v', '5',
            poster_path,
        ], capture_output=True, check=True)
        return poster_path
    except Exception:
        return None


def generate_video_variant(source_path, filename, profile_name):
    profile = VIDEO_RENDITION_PROFILES.get(profile_name)
    if not profile:
        return None
    os.makedirs(VIDEO_VARIANT_FOLDER, exist_ok=True)
    variant_path = get_video_variant_path(filename, profile_name)
    scale_expr = (
        f'scale=w=min(iw\\,{profile["width"]}):h=min(ih\\,{profile["height"]}):'
        'force_original_aspect_ratio=decrease'
    )
    try:
        subprocess.run([
            'ffmpeg', '-y',
            '-i', source_path,
            '-vf', scale_expr,
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-profile:v', 'high',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-b:v', profile['video_bitrate'],
            '-maxrate', profile['video_bitrate'],
            '-bufsize', str(int(profile['video_bitrate'][:-1]) * 2) + 'k',
            '-c:a', 'aac',
            '-b:a', profile['audio_bitrate'],
            variant_path,
        ], capture_output=True, check=True)
        return variant_path
    except Exception:
        return None


def ensure_image_thumbnail(filename):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    thumb_url = get_thumbnail_url(filename)
    if thumb_url:
        return thumb_url
    if generate_image_thumbnail(source_path, filename):
        return get_thumbnail_url(filename)
    return None


def ensure_image_rendition(filename, profile_name):
    if profile_name not in IMAGE_RENDITION_PROFILES:
        return None
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    rendition_url = get_image_rendition_url(filename, profile_name)
    if rendition_url:
        return rendition_url
    if generate_image_rendition(source_path, filename, profile_name):
        return get_image_rendition_url(filename, profile_name)
    return None


def ensure_image_variant(filename, width, height):
    bounds = _normalize_variant_bounds(width, height)
    if not bounds:
        return None
    width, height = bounds
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    variant_url = get_image_variant_url(filename, width, height)
    if variant_url:
        return variant_url
    if generate_image_variant(source_path, filename, width, height):
        return get_image_variant_url(filename, width, height)
    return None


def ensure_video_thumbnail(filename):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    thumb_url = get_thumbnail_url(filename)
    if thumb_url:
        return thumb_url
    if generate_video_thumbnail(source_path, filename):
        return get_thumbnail_url(filename)
    return None


def ensure_video_poster(filename, profile_name):
    if profile_name not in VIDEO_POSTER_PROFILES:
        return None
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    poster_url = get_video_poster_url(filename, profile_name)
    if poster_url:
        return poster_url
    if generate_video_poster(source_path, filename, profile_name):
        return get_video_poster_url(filename, profile_name)
    return None


def ensure_video_variant(filename, profile_name):
    if profile_name not in VIDEO_RENDITION_PROFILES:
        return None
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return None
    variant_url = get_video_variant_url(filename, profile_name)
    if variant_url:
        return variant_url
    if generate_video_variant(source_path, filename, profile_name):
        return get_video_variant_url(filename, profile_name)
    return None


def get_image_dimensions(filename):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return 0, 0
    try:
        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img)
            return _normalize_dimension(img.width), _normalize_dimension(img.height)
    except Exception:
        return 0, 0


def get_video_dimensions(filename):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return 0, 0
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', source_path
        ], capture_output=True, text=True, check=True)
        info = json.loads(result.stdout)
        for stream in info.get('streams', []):
            if stream.get('codec_type') != 'video':
                continue
            return (
                _normalize_dimension(stream.get('width')),
                _normalize_dimension(stream.get('height')),
            )
    except Exception:
        return 0, 0
    return 0, 0


def _eligible_image_profiles(filename):
    width, height = get_image_dimensions(filename)
    if width <= 0 or height <= 0:
        return []
    eligible = []
    longest_edge = max(width, height)
    for profile_name, profile in IMAGE_RENDITION_PROFILES.items():
        if longest_edge >= min(profile['max_width'], profile['max_height']):
            eligible.append(profile_name)
    return eligible or ['thumb']


def _eligible_video_profiles(filename):
    width, height = get_video_dimensions(filename)
    if width <= 0 or height <= 0:
        return []
    longest_edge = max(width, height)
    shortest_edge = min(width, height)
    eligible = []
    for profile_name in DISPLAY_VIDEO_PROFILES:
        profile = VIDEO_RENDITION_PROFILES[profile_name]
        if longest_edge >= max(profile['width'], profile['height']) and shortest_edge >= min(profile['width'], profile['height']):
            eligible.append(profile_name)
    return eligible


def generate_standard_image_renditions(filename, *, force=False):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return []
    generated = []
    if force or not get_thumbnail_url(filename):
        if generate_image_thumbnail(source_path, filename):
            generated.append('legacy-thumb')
    for profile_name in _eligible_image_profiles(filename):
        if not force and get_existing_image_rendition_url(filename, profile_name):
            continue
        if generate_image_rendition(source_path, filename, profile_name):
            generated.append(profile_name)
    return generated


def generate_standard_video_renditions(filename, *, force=False):
    source_path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(source_path):
        return []
    generated = []
    if force or not get_existing_thumbnail_url(filename):
        if generate_video_thumbnail(source_path, filename):
            generated.append('legacy-thumb')
    for profile_name in get_video_poster_profile_names():
        if not force and get_existing_video_poster_url(filename, profile_name):
            continue
        if generate_video_poster(source_path, filename, profile_name):
            generated.append(f'poster:{profile_name}')
    for profile_name in _eligible_video_profiles(filename):
        if not force and get_existing_video_variant_url(filename, profile_name):
            continue
        if generate_video_variant(source_path, filename, profile_name):
            generated.append(profile_name)
    return generated


def generate_standard_renditions(filename, *, force=False):
    media_type = get_media_type(filename)
    if media_type == 'image':
        return generate_standard_image_renditions(filename, force=force)
    if media_type == 'video':
        return generate_standard_video_renditions(filename, force=force)
    return []


def _pick_image_profile(context='admin', bounds=None):
    if context == 'display' and bounds:
        target = max(bounds[0], bounds[1])
        if target <= 320:
            return 'thumb'
        if target <= 640:
            return 'small'
        if target <= 1280:
            return 'medium'
        if target <= 1920:
            return 'large'
        return 'xlarge'
    return DEFAULT_CONTEXTS.get(context, DEFAULT_CONTEXTS['admin'])['image_profile']


def _pick_video_profile(context='admin', bounds=None):
    if context == 'display' and bounds:
        target = max(bounds[0], bounds[1])
        if target >= 3840:
            return 'v2160'
        return 'v1080'
    return DEFAULT_CONTEXTS.get(context, DEFAULT_CONTEXTS['admin'])['video_profile']


def _video_profile_fallbacks(profile_name):
    if profile_name == 'v2160':
        return ('v2160', 'v1080')
    return (profile_name,)


def _pick_video_poster_profile(context='admin', bounds=None):
    if context == 'display' and bounds:
        image_profile = _pick_image_profile(context=context, bounds=bounds)
        return 'large' if image_profile in ('large', 'xlarge') else image_profile
    return DEFAULT_CONTEXTS.get(context, DEFAULT_CONTEXTS['admin'])['video_poster_profile']

def get_media_url(filename, *, context='admin', bounds=None, allow_original=False, generate_missing=False):
    try:
        media_type = get_media_type(filename)
        if media_type == 'image':
            profile_name = _pick_image_profile(context=context, bounds=bounds)
            image_url = (
                ensure_image_rendition(filename, profile_name)
                if generate_missing else
                get_existing_image_rendition_url(filename, profile_name)
            )
            if image_url:
                return image_url
            legacy_thumb = ensure_image_thumbnail(filename) if generate_missing else get_existing_thumbnail_url(filename)
            return get_original_media_url(filename) if allow_original else legacy_thumb
        if media_type == 'video':
            if context in ('admin', 'campaign'):
                poster_profile = _pick_video_poster_profile(context=context, bounds=bounds)
                poster_url = (
                    ensure_video_poster(filename, poster_profile)
                    if generate_missing else
                    get_existing_video_poster_url(filename, poster_profile)
                )
                if poster_url:
                    return poster_url
                legacy_thumb = ensure_video_thumbnail(filename) if generate_missing else get_existing_thumbnail_url(filename)
                return legacy_thumb or ('/static/images/logo.svg' if not allow_original else get_original_media_url(filename))
            video_profile = _pick_video_profile(context=context, bounds=bounds)
            # Video transcoding is intentionally left to the background worker.
            # HTTP requests should never block on generating a missing rendition.
            for candidate_profile in _video_profile_fallbacks(video_profile):
                video_url = get_existing_video_variant_url(filename, candidate_profile)
                if video_url:
                    return video_url
            if allow_original:
                return get_original_media_url(filename)
            return get_existing_thumbnail_url(filename)
        return get_original_media_url(filename) if allow_original else None
    except Exception:
        if get_media_type(filename) == 'video':
            legacy_thumb = ensure_video_thumbnail(filename) if generate_missing else get_existing_thumbnail_url(filename)
            return legacy_thumb or ('/static/images/logo.svg' if not allow_original else get_original_media_url(filename))
        if get_media_type(filename) == 'image':
            legacy_thumb = ensure_image_thumbnail(filename) if generate_missing else get_existing_thumbnail_url(filename)
            return legacy_thumb or (get_original_media_url(filename) if allow_original else None)
        return get_original_media_url(filename) if allow_original else None


def build_media_preview_map(files, context='admin', *, generate_missing=False):
    metadata = build_media_metadata_map(
        files,
        preview_contexts=(context,),
        generate_missing=generate_missing,
    )
    return {
        filename: metadata.get(filename, {}).get('preview_urls', {}).get(context) or '/static/images/logo.svg'
        for filename in files
    }


def is_safe_svg_file(path):
    try:
        with open(path, encoding='utf-8', errors='ignore') as handle:
            content = handle.read(200_000)
    except OSError:
        return False
    lowered = content.lower()
    forbidden = ('<script', 'javascript:', 'onload=', 'onerror=', '<foreignobject')
    return '<svg' in lowered and not any(token in lowered for token in forbidden)


def are_videos_enabled(cfg=None):
    cfg = cfg or load_config()
    return bool(cfg.get("features", {}).get("videos", True))


def is_media_allowed_by_features(filename, cfg=None):
    media_type = get_media_type(filename)
    if media_type == 'video' and not are_videos_enabled(cfg):
        return False
    return True


def _all_media_config_signature(cfg):
    return (
        tuple(str(filename) for filename in cfg.get("order", []) if isinstance(filename, str)),
        bool(cfg.get("features", {}).get("videos", True)),
    )


def _scan_all_media(cfg):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    files = [
        f for f in os.listdir(UPLOAD_FOLDER)
        if f.lower().endswith(MEDIA_EXTS)
    ]
    files = [f for f in files if is_media_allowed_by_features(f, cfg)]
    order = cfg.get("order", [])
    ordered = [f for f in order if f in files]
    unordered = [f for f in files if f not in ordered]
    return ordered + unordered


def get_all_media(cfg=None):
    cfg = cfg or load_config()
    cache_key = (_all_media_config_signature(cfg), make_media_revision())
    with _ALL_MEDIA_CACHE_LOCK:
        cached = _ALL_MEDIA_CACHE.get(cache_key)
        if cached is not None:
            return list(cached)

    files = _scan_all_media(cfg)
    with _ALL_MEDIA_CACHE_LOCK:
        _ALL_MEDIA_CACHE[cache_key] = tuple(files)
        while len(_ALL_MEDIA_CACHE) > _ALL_MEDIA_CACHE_MAX_ENTRIES:
            _ALL_MEDIA_CACHE.pop(next(iter(_ALL_MEDIA_CACHE)))
    return list(files)


def normalize_group_name(name):
    cleaned = " ".join(str(name or "").split())
    return cleaned[:48]


def get_media_groups(filename, cfg=None):
    cfg = cfg or load_config()
    groups_map = cfg.get("groups", {})
    groups = groups_map.get(filename, [])
    if not isinstance(groups, list):
        return []
    normalized = []
    seen = set()
    for group in groups:
        group_name = normalize_group_name(group)
        if group_name and group_name not in seen:
            normalized.append(group_name)
            seen.add(group_name)
    return normalized


def collect_defined_group_names(cfg):
    groups_map = cfg.get("groups", {})
    if not isinstance(groups_map, dict):
        return set()
    names = set()
    for groups in groups_map.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            group_name = normalize_group_name(group)
            if group_name:
                names.add(group_name)
    return names


def cleanup_orphan_group_metadata(cfg):
    active_groups = collect_defined_group_names(cfg)
    cfg["disabled_groups"] = [
        group for group in cfg.get("disabled_groups", [])
        if normalize_group_name(group) in active_groups
    ]
    for screen_cfg in cfg.get("screens", {}).values():
        if not isinstance(screen_cfg, dict):
            continue
        screen_cfg["disabled_groups"] = [
            group for group in screen_cfg.get("disabled_groups", [])
            if normalize_group_name(group) in active_groups
        ]
    for key in ("group_pools", "group_screens"):
        entries = cfg.get(key, {})
        if isinstance(entries, dict):
            cfg[key] = {
                group: value for group, value in entries.items()
                if normalize_group_name(group) in active_groups
            }


def is_media_disabled(filename, cfg):
    if filename in cfg.get("disabled", []):
        return True
    disabled_groups = set(cfg.get("disabled_groups", []))
    if not disabled_groups:
        return False
    return any(group in disabled_groups for group in get_media_groups(filename, cfg))


def get_group_active_screens(group_name, cfg):
    """Return the list of screens this group is linked to (empty = global)."""
    return cfg.get("group_screens", {}).get(group_name, [])


def is_group_active_on_screen(group_name, cfg, screen):
    """True if the group is active on the given screen (globally or explicitly linked)."""
    screens = get_group_active_screens(group_name, cfg)
    return not screens or screen in screens


def collect_group_states(files, cfg, screen=None):
    disabled_groups = set(cfg.get("disabled_groups", []))
    group_pools = cfg.get("group_pools", {})
    counts = {}
    for filename in files:
        for group in get_media_groups(filename, cfg):
            if screen is not None and not is_group_active_on_screen(group, cfg, screen):
                continue
            counts[group] = counts.get(group, 0) + 1
    return [
        {
            "name": group,
            "count": counts[group],
            "disabled": group in disabled_groups,
            "pool_size": group_pools.get(group, 0),
            "screens": get_group_active_screens(group, cfg),
        }
        for group in sorted(counts, key=str.casefold)
    ]


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
    if time_end and not time_start and not date_start and not date_end:
        return True
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
    global _DISK_USAGE_CACHE, _DISK_USAGE_CACHE_EXPIRES_AT

    now = time.monotonic()
    with _DISK_USAGE_CACHE_LOCK:
        if _DISK_USAGE_CACHE is not None and now < _DISK_USAGE_CACHE_EXPIRES_AT:
            return dict(_DISK_USAGE_CACHE)

    media_bytes = 0
    for folder in (UPLOAD_FOLDER, VIDEO_THUMB_FOLDER, IMAGE_VARIANT_FOLDER,
                   VIDEO_VARIANT_FOLDER, VIDEO_POSTER_FOLDER):
        if not os.path.isdir(folder):
            continue
        for dirpath, _, filenames in os.walk(folder):
            for fname in filenames:
                try:
                    media_bytes += os.path.getsize(os.path.join(dirpath, fname))
                except OSError:
                    pass

    stat = shutil.disk_usage(UPLOAD_FOLDER)
    usage = {
        "total": round(stat.total / (1024**3), 1),
        "used":  round(media_bytes / (1024**3), 1),
        "free":  round(stat.free  / (1024**3), 1),
    }
    with _DISK_USAGE_CACHE_LOCK:
        _DISK_USAGE_CACHE = dict(usage)
        _DISK_USAGE_CACHE_EXPIRES_AT = time.monotonic() + _DISK_USAGE_CACHE_TTL_SECONDS
    return usage


def _size_label(size_bytes, media_type='unknown'):
    if media_type == 'video':
        return f"{round(size_bytes / 1024 / 1024, 1)} Mo"
    return f"{round(size_bytes / 1024)} Ko"


def _metadata_cache_key(filename, stat_result, preview_contexts, generate_missing):
    return (
        filename,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        tuple(preview_contexts),
        bool(generate_missing),
        make_media_revision(),
    )


def _metadata_snapshot(metadata):
    snapshot = dict(metadata)
    snapshot['dimensions'] = dict(metadata.get('dimensions') or {})
    snapshot['preview_urls'] = dict(metadata.get('preview_urls') or {})
    return snapshot


def _build_media_metadata(filename, stat_result, preview_contexts, generate_missing):
    media_type = get_media_type(filename)
    width = 0
    height = 0
    if media_type == 'image':
        width, height = get_image_dimensions(filename)
    elif media_type == 'video':
        width, height = get_video_dimensions(filename)

    dims_label = f'{width}x{height}' if width and height else media_type if media_type != 'unknown' else '--'
    preview_urls = {}
    for context in preview_contexts:
        preview_urls[context] = get_media_url(
            filename,
            context=context,
            allow_original=context in ('preview', 'display'),
            generate_missing=generate_missing,
        ) or '/static/images/logo.svg'
    original_url = get_original_media_url(filename)
    if original_url:
        preview_urls['original'] = original_url

    return {
        'filename': filename,
        'type': media_type,
        'size_bytes': stat_result.st_size,
        'size': _size_label(stat_result.st_size, media_type),
        'mtime': stat_result.st_mtime,
        'mtime_ns': stat_result.st_mtime_ns,
        'modified_at': datetime.fromtimestamp(stat_result.st_mtime).isoformat(timespec='minutes'),
        'dimensions': {'width': width, 'height': height},
        'width': width,
        'height': height,
        'dims': dims_label,
        'preview_urls': preview_urls,
    }


def get_media_metadata(filename, *, preview_contexts=('admin',), generate_missing=False):
    path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        stat_result = os.stat(path)
    except OSError:
        return {
            'filename': filename,
            'type': 'unknown',
            'size_bytes': 0,
            'size': '--',
            'mtime': 0,
            'mtime_ns': 0,
            'modified_at': '',
            'dimensions': {'width': 0, 'height': 0},
            'width': 0,
            'height': 0,
            'dims': '--',
            'preview_urls': {},
        }

    preview_contexts = tuple(dict.fromkeys(str(context) for context in preview_contexts if context))
    cache_key = _metadata_cache_key(filename, stat_result, preview_contexts, generate_missing)
    with _MEDIA_METADATA_CACHE_LOCK:
        cached = _MEDIA_METADATA_CACHE.get(cache_key)
        if cached is not None:
            return _metadata_snapshot(cached)

    metadata = _build_media_metadata(filename, stat_result, preview_contexts, generate_missing)
    with _MEDIA_METADATA_CACHE_LOCK:
        _MEDIA_METADATA_CACHE[cache_key] = _metadata_snapshot(metadata)
        while len(_MEDIA_METADATA_CACHE) > _MEDIA_METADATA_CACHE_MAX_ENTRIES:
            _MEDIA_METADATA_CACHE.pop(next(iter(_MEDIA_METADATA_CACHE)))
    return _metadata_snapshot(metadata)


def build_media_metadata_map(files, *, preview_contexts=('admin',), generate_missing=False):
    return {
        filename: get_media_metadata(
            filename,
            preview_contexts=preview_contexts,
            generate_missing=generate_missing,
        )
        for filename in files
    }


def clear_media_metadata_cache():
    with _MEDIA_METADATA_CACHE_LOCK:
        _MEDIA_METADATA_CACHE.clear()


def get_file_info(filename, *, include_dimensions=True):
    path = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(path):
        return {"size": "--", "dims": "--", "type": "unknown"}
    metadata = get_media_metadata(filename, preview_contexts=())
    if not include_dimensions:
        dims = metadata['type'] if metadata['type'] != 'unknown' else '--'
        return {"size": metadata["size"], "dims": dims, "type": metadata["type"]}
    return {"size": metadata["size"], "dims": metadata["dims"], "type": metadata["type"]}


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
