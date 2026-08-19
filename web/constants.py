# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os


def _env_int(name, default):
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_app_path(*parts):
    return os.path.join(BASE_DIR, *parts)


def _resolve_required_env_path(name):
    configured = os.environ.get(name, '').strip()
    if configured:
        if os.path.isabs(configured):
            return configured
        return _resolve_app_path(configured)
    raise RuntimeError(f"{name} absent. Lancez le module d'installation ou renseignez .env.")


def _resolve_data_dir():
    return _resolve_required_env_path('PRIVATE_DIR')


STATIC_MEDIA_DIR = _resolve_required_env_path('MEDIA_DIR')
LEGACY_STATIC_MEDIA_DIR = _resolve_app_path('static', 'media')
ORIGINAL_MEDIA_SUBDIR = 'original'
STATIC_MEDIA_URL = '/static/data'
ORIGINAL_MEDIA_URL = f'{STATIC_MEDIA_URL}/{ORIGINAL_MEDIA_SUBDIR}'

UPLOAD_FOLDER = os.path.join(STATIC_MEDIA_DIR, ORIGINAL_MEDIA_SUBDIR)
VIDEO_THUMB_FOLDER = os.path.join(STATIC_MEDIA_DIR, 'thumbnails')
IMAGE_VARIANT_FOLDER = os.path.join(STATIC_MEDIA_DIR, 'variants')
VIDEO_VARIANT_FOLDER = os.path.join(STATIC_MEDIA_DIR, 'video_variants')
VIDEO_POSTER_FOLDER = os.path.join(STATIC_MEDIA_DIR, 'video_posters')
LEGACY_VIDEO_THUMB_FOLDER = os.path.join(STATIC_MEDIA_DIR, '.thumbs')
LEGACY_IMAGE_VARIANT_FOLDER = os.path.join(STATIC_MEDIA_DIR, '.variants')
LEGACY_VIDEO_VARIANT_FOLDER = os.path.join(STATIC_MEDIA_DIR, '.video_variants')
LEGACY_VIDEO_POSTER_FOLDER = os.path.join(STATIC_MEDIA_DIR, '.video_posters')
IMAGES_FOLDER = _resolve_app_path('static', 'images')
PRIVATE_DATA_DIR = _resolve_data_dir()
DEFAULT_LOGO  = 'logo.svg'
LOGO_EXTS     = {'.svg', '.png', '.jpg', '.jpeg'}

MAX_WIDTH  = 1920
MAX_HEIGHT = 1080
MAX_FILE_UPLOAD_SIZE = 150 * 1024 * 1024
MAX_BATCH_UPLOAD_SIZE = 256 * 1024 * 1024
MAX_UPLOAD_PDF_PAGES = max(1, _env_int('MAX_UPLOAD_PDF_PAGES', 80))
MAX_UPLOAD_IMAGE_PIXELS = max(1, _env_int('MAX_UPLOAD_IMAGE_PIXELS', 50_000_000))
MAX_UPLOAD_VIDEO_SECONDS = max(1, _env_int('MAX_UPLOAD_VIDEO_SECONDS', 3 * 60 * 60))
MEDIA_PROBE_TIMEOUT_SECONDS = max(1, _env_int('MEDIA_PROBE_TIMEOUT_SECONDS', 15))
MEDIA_CONVERT_TIMEOUT_SECONDS = max(1, _env_int('MEDIA_CONVERT_TIMEOUT_SECONDS', 120))
ACTIVITY_LOG_RETENTION_DAYS = max(1, _env_int('ACTIVITY_LOG_RETENTION_DAYS', 90))
ACTIVITY_LOG_MAX_ROWS = max(1000, _env_int('ACTIVITY_LOG_MAX_ROWS', 20000))
ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS = max(60, _env_int('ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS', 3600))
ACTIVITY_LOG_VACUUM_INTERVAL_SECONDS = max(
    ACTIVITY_LOG_CLEANUP_INTERVAL_SECONDS,
    _env_int('ACTIVITY_LOG_VACUUM_INTERVAL_SECONDS', 86400),
)

IMAGE_EXTS = ('.jpg', '.jpeg', '.png')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')
MEDIA_EXTS = IMAGE_EXTS + VIDEO_EXTS

LAT               = 42.6977
LNG               = 2.8956
DEFAULT_METEO_VILLE = "Perpignan"
DEFAULT_METEO_TZ    = "Europe/Paris"

SCHOOL_ZONES = (
    ("auto", "Auto"),
    ("A", "Zone A"),
    ("B", "Zone B"),
    ("C", "Zone C"),
    ("Corse", "Corse"),
    ("Guadeloupe", "Guadeloupe"),
    ("Guyane", "Guyane"),
    ("Martinique", "Martinique"),
    ("Mayotte", "Mayotte"),
    ("Nouvelle Caledonie", "Nouvelle-Calédonie"),
    ("Polynesie", "Polynésie"),
    ("Reunion", "La Réunion"),
    ("Saint-Pierre-et-Miquelon", "Saint-Pierre-et-Miquelon"),
    ("Wallis et Futuna", "Wallis-et-Futuna"),
)

ALL_PERMISSIONS = [
    ("upload",         "perm_upload"),
    ("announcements", "perm_announcements"),
    ("menus",          "perm_menus"),
    ("delete",         "perm_delete"),
    ("reorder",        "perm_reorder"),
    ("toggle",         "perm_toggle"),
    ("duration",       "perm_duration"),
    ("compress",       "perm_compress"),
    ("logo",           "perm_logo"),
    ("schedule",       "perm_schedule"),
    ("cleanup",        "perm_cleanup"),
    ("priority_alert", "perm_priority_alert"),
]

ALL_FEATURES = [
    ("upload",         "feature_upload",         "feature_upload_desc"),
    ("announcements",  "feature_announcements",  "feature_announcements_desc"),
    ("menus",          "feature_menus",          "feature_menus_desc"),
    ("videos",         "feature_videos",         "feature_videos_desc"),
    ("delete",         "feature_delete",          "feature_delete_desc"),
    ("compress",       "feature_compress",        "feature_compress_desc"),
    ("ephemeris",      "feature_ephemeris",       "feature_ephemeris_desc"),
    ("campaigns",      "feature_campaigns",       "feature_campaigns_desc"),
    ("schedule",       "feature_schedule",        "feature_schedule_desc"),
    ("groups",         "feature_groups",          "feature_groups_desc"),
    ("screens",        "feature_screens",         "feature_screens_desc"),
    ("priority_alert", "feature_priority_alert",  "feature_priority_alert_desc"),
    ("activity",       "feature_activity",        "feature_activity_desc"),
]

RESERVED_SCREEN_NAMES = {'default', 'admin', 'api', 'static', 'login', 'logout'}

VALID_THEMES = ('violet', 'bleu', 'sombre')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(VIDEO_THUMB_FOLDER, exist_ok=True)
os.makedirs(IMAGE_VARIANT_FOLDER, exist_ok=True)
os.makedirs(VIDEO_VARIANT_FOLDER, exist_ok=True)
os.makedirs(VIDEO_POSTER_FOLDER, exist_ok=True)
os.makedirs(PRIVATE_DATA_DIR, exist_ok=True)
