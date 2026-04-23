# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

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


def _resolve_data_dir():
    configured = os.environ.get('VISIO_DATA_DIR')
    if not configured:
        return _resolve_app_path('data', 'private')
    if os.path.isabs(configured):
        return configured
    return _resolve_app_path(configured)


STATIC_MEDIA_DIR = _resolve_app_path('static', 'data')
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
DB_FILE       = os.path.join(PRIVATE_DATA_DIR, 'visio-display.db')
CONFIG_FILE   = os.path.join(PRIVATE_DATA_DIR, 'config.json')
QUEUE_FILE    = os.path.join(PRIVATE_DATA_DIR, 'queue.json')
USERS_FILE    = os.path.join(PRIVATE_DATA_DIR, 'users.json')
LEGACY_DB_FILE     = os.path.join(STATIC_MEDIA_DIR, 'visio-display.db')
LEGACY_CONFIG_FILE = os.path.join(STATIC_MEDIA_DIR, 'config.json')
LEGACY_QUEUE_FILE  = os.path.join(STATIC_MEDIA_DIR, 'queue.json')
LEGACY_USERS_FILE  = os.path.join(STATIC_MEDIA_DIR, 'users.json')
DEFAULT_LOGO  = 'logo.svg'
LOGO_EXTS     = {'.svg', '.png', '.jpg', '.jpeg'}

MAX_WIDTH  = 1920
MAX_HEIGHT = 1080
MAX_FILE_UPLOAD_SIZE = 150 * 1024 * 1024
MAX_BATCH_UPLOAD_SIZE = 256 * 1024 * 1024
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
    ("upload",    "perm_upload"),
    ("delete",    "perm_delete"),
    ("reorder",   "perm_reorder"),
    ("toggle",    "perm_toggle"),
    ("duration",  "perm_duration"),
    ("compress",  "perm_compress"),
    ("logo",      "perm_logo"),
    ("ephemeris", "perm_ephemeris"),
    ("schedule",  "perm_schedule"),
]

ALL_FEATURES = [
    ("upload",         "feature_upload",         "feature_upload_desc"),
    ("videos",         "feature_videos",         "feature_videos_desc"),
    ("delete",         "feature_delete",          "feature_delete_desc"),
    ("compress",       "feature_compress",        "feature_compress_desc"),
    ("ephemeris",      "feature_ephemeris",       "feature_ephemeris_desc"),
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
