import os

UPLOAD_FOLDER = 'static/data'
IMAGES_FOLDER = 'static/images'
DB_FILE       = 'static/data/ramses.db'
CONFIG_FILE   = 'static/data/config.json'
QUEUE_FILE    = 'static/data/queue.json'
USERS_FILE    = 'static/data/users.json'
DEFAULT_LOGO  = 'logo.svg'
LOGO_EXTS     = {'.svg', '.png', '.jpg', '.jpeg'}

MAX_WIDTH  = 1920
MAX_HEIGHT = 1080

IMAGE_EXTS = ('.jpg', '.jpeg', '.png')
VIDEO_EXTS = ('.mp4', '.webm', '.mov', '.avi', '.mkv')
MEDIA_EXTS = IMAGE_EXTS + VIDEO_EXTS

LAT               = 42.6977
LNG               = 2.8956
DEFAULT_METEO_VILLE = "Perpignan"
DEFAULT_METEO_TZ    = "Europe/Paris"

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

RESERVED_SCREEN_NAMES = {'default', 'admin', 'api', 'static', 'login', 'logout'}

VALID_THEMES = ('violet', 'bleu', 'sombre')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
