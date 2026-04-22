# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import os

UPLOAD_FOLDER = 'static/data'
IMAGES_FOLDER = 'static/images'
PRIVATE_DATA_DIR = os.environ.get('VISIO_DATA_DIR', 'data/private')
DB_FILE       = os.path.join(PRIVATE_DATA_DIR, 'visio-display.db')
CONFIG_FILE   = os.path.join(PRIVATE_DATA_DIR, 'config.json')
QUEUE_FILE    = os.path.join(PRIVATE_DATA_DIR, 'queue.json')
USERS_FILE    = os.path.join(PRIVATE_DATA_DIR, 'users.json')
LEGACY_DB_FILE     = os.path.join(UPLOAD_FOLDER, 'visio-display.db')
LEGACY_CONFIG_FILE = os.path.join(UPLOAD_FOLDER, 'config.json')
LEGACY_QUEUE_FILE  = os.path.join(UPLOAD_FOLDER, 'queue.json')
LEGACY_USERS_FILE  = os.path.join(UPLOAD_FOLDER, 'users.json')
DEFAULT_LOGO  = 'logo.svg'
LOGO_EXTS     = {'.svg', '.png', '.jpg', '.jpeg'}

MAX_WIDTH  = 1920
MAX_HEIGHT = 1080
MAX_FILE_UPLOAD_SIZE = 16 * 1024 * 1024
MAX_BATCH_UPLOAD_SIZE = 256 * 1024 * 1024

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
os.makedirs(PRIVATE_DATA_DIR, exist_ok=True)
