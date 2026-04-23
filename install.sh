# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

#!/bin/bash

set -e

SCRIPT_PATH="$(realpath "$0")"
USER_NAME_INPUT="${VISIO_USER_NAME:-}"
SERVER_URL_INPUT="${VISIO_SERVER_URL:-}"
SCREEN_NAME_INPUT="${VISIO_SCREEN_NAME:-}"
MACHINE_NAME_INPUT="${VISIO_MACHINE_NAME:-}"
AUTO_REBOOT=1

while [ $# -gt 0 ]; do
    case "$1" in
        --user)
            shift
            USER_NAME_INPUT="${1:-}"
            ;;
        --user=*)
            USER_NAME_INPUT="${1#*=}"
            ;;
        --server-url)
            shift
            SERVER_URL_INPUT="${1:-}"
            ;;
        --server-url=*)
            SERVER_URL_INPUT="${1#*=}"
            ;;
        --screen-name)
            shift
            SCREEN_NAME_INPUT="${1:-}"
            ;;
        --screen-name=*)
            SCREEN_NAME_INPUT="${1#*=}"
            ;;
        --machine-name)
            shift
            MACHINE_NAME_INPUT="${1:-}"
            ;;
        --machine-name=*)
            MACHINE_NAME_INPUT="${1#*=}"
            ;;
        --no-reboot)
            AUTO_REBOOT=0
            ;;
        -h|--help)
            cat <<'EOF'
Usage: install.sh [--user NOM_UTILISATEUR] [--server-url URL] [--screen-name NOM] [--machine-name NOM] [--no-reboot]

Options:
  --user NOM_UTILISATEUR  Utilisateur local a configurer pour l'autologin/kiosk
  --server-url URL        URL du serveur a ouvrir au demarrage du client
  --screen-name NOM       Nom d'ecran a enregistrer dans la configuration client
  --machine-name NOM      Nom d'hote Linux a appliquer sur la machine cliente
  --no-reboot             N'effectue pas le reboot final automatiquement
EOF
            exit 0
            ;;
        *)
            echo "Option inconnue : $1"
            exit 1
            ;;
    esac
    shift
done

if [ "$(id -u)" -ne 0 ]; then
    REEXEC_CMD="bash $(printf '%q' "$SCRIPT_PATH")"
    if [ -n "$USER_NAME_INPUT" ]; then
        REEXEC_CMD="$REEXEC_CMD --user $(printf '%q' "$USER_NAME_INPUT")"
    fi
    if [ -n "$SERVER_URL_INPUT" ]; then
        REEXEC_CMD="$REEXEC_CMD --server-url $(printf '%q' "$SERVER_URL_INPUT")"
    fi
    if [ -n "$SCREEN_NAME_INPUT" ]; then
        REEXEC_CMD="$REEXEC_CMD --screen-name $(printf '%q' "$SCREEN_NAME_INPUT")"
    fi
    if [ -n "$MACHINE_NAME_INPUT" ]; then
        REEXEC_CMD="$REEXEC_CMD --machine-name $(printf '%q' "$MACHINE_NAME_INPUT")"
    fi
    if [ "$AUTO_REBOOT" -eq 0 ]; then
        REEXEC_CMD="$REEXEC_CMD --no-reboot"
    fi
    exec su -c "$REEXEC_CMD"
fi

if [ -n "$USER_NAME_INPUT" ]; then
    USER_NAME="$USER_NAME_INPUT"
    echo "==> Utilisateur preconfigure : $USER_NAME"
else
    echo "==> Choix de l'utilisateur à configurer"
    read -rp "Nom de l'utilisateur local pour l'autologin/kiosk : " USER_NAME
fi

if [ -z "$USER_NAME" ] || [ "$USER_NAME" = "root" ]; then
    echo "Utilisateur invalide."
    exit 1
fi

if ! id "$USER_NAME" >/dev/null 2>&1; then
    echo "Utilisateur introuvable : $USER_NAME"
    exit 1
fi

if [ -n "$MACHINE_NAME_INPUT" ]; then
    MACHINE_NAME_INPUT="$(printf '%s' "$MACHINE_NAME_INPUT" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g' | cut -c1-63)"
    if [ -z "$MACHINE_NAME_INPUT" ]; then
        echo "Nom de machine invalide."
        exit 1
    fi
fi

USER_HOME="$(eval echo "~$USER_NAME")"
VISIO_DIR="/opt/visio"
CONFIG_DIR="/etc/visio"
CONFIG_FILE="$CONFIG_DIR/client.conf"

echo "==> Désactivation dépôt cdrom si présent"
[ -f /etc/apt/sources.list ] && sed -i 's|^deb cdrom:|#deb cdrom:|g' /etc/apt/sources.list

echo "==> Installation des paquets"
apt update
apt install -y \
  curl xorg xinit openbox firefox-esr xterm unclutter \
  xserver-xorg-legacy x11-xserver-utils polkitd

echo "==> Création des dossiers"
mkdir -p \
  "$VISIO_DIR" \
  "$CONFIG_DIR" \
  /etc/systemd/system/getty@tty1.service.d \
  /etc/X11 \
  /etc/polkit-1/rules.d

echo "==> Préparation du fichier de configuration"
touch "$CONFIG_FILE"
chown "$USER_NAME:$USER_NAME" "$CONFIG_FILE"
chmod 664 "$CONFIG_FILE"

if [ -n "$MACHINE_NAME_INPUT" ]; then
    echo "==> Configuration du nom de machine : $MACHINE_NAME_INPUT"
    hostnamectl set-hostname "$MACHINE_NAME_INPUT" 2>/dev/null || echo "$MACHINE_NAME_INPUT" > /etc/hostname
    if [ -f /etc/hosts ]; then
        sed -i -E "s/^127\.0\.1\.1[[:space:]]+.*/127.0.1.1\t$MACHINE_NAME_INPUT/" /etc/hosts || true
        if ! grep -Eq '^127\.0\.1\.1[[:space:]]+' /etc/hosts; then
            printf '127.0.1.1\t%s\n' "$MACHINE_NAME_INPUT" >> /etc/hosts
        fi
    fi
fi

if [ -n "$SERVER_URL_INPUT" ]; then
    echo "==> Préconfiguration du client"
    cat > "$CONFIG_FILE" <<EOC
SERVER_URL=$SERVER_URL_INPUT
SCREEN_NAME=$SCREEN_NAME_INPUT
WATCHDOG_CHECK_INTERVAL=30
WATCHDOG_GRACE_PERIOD=90
WATCHDOG_FAILURES_BEFORE_REBOOT=1
FIREFOX_RESTART_INTERVAL_SECONDS=21600
EOC
fi

echo "==> Configuration Xwrapper"
cat > /etc/X11/Xwrapper.config <<'EOF'
allowed_users=anybody
needs_root_rights=yes
EOF

echo "==> Autorisation reboot/poweroff pour $USER_NAME"
cat > /etc/polkit-1/rules.d/49-visio-power.rules <<EOF
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.login1.power-off" ||
         action.id == "org.freedesktop.login1.reboot") &&
        subject.user == "$USER_NAME") {
        return polkit.Result.YES;
    }
});
EOF
chmod 644 /etc/polkit-1/rules.d/49-visio-power.rules

echo "==> Création bootstrap.sh"
cat > "$VISIO_DIR/bootstrap.sh" <<'EOF'
#!/bin/bash

CONFIG="/etc/visio/client.conf"
TMP_URL="/tmp/visio_url_input"
TMP_NAME="/tmp/visio_name_input"

rm -f "$TMP_URL" "$TMP_NAME"

xterm -fa Monospace -fs 14 -fullscreen -bg black -fg green -e bash -c '
clear
echo
echo "========================================"
echo "        CONFIGURATION VISIO"
echo "========================================"
echo
read -rp "Entrez l URL du serveur : " URL
read -rp "Nom de l ecran (optionnel) : " NAME
echo "$URL" > /tmp/visio_url_input
echo "$NAME" > /tmp/visio_name_input
'

URL="$(cat "$TMP_URL" 2>/dev/null || true)"
NAME="$(cat "$TMP_NAME" 2>/dev/null || true)"
rm -f "$TMP_URL" "$TMP_NAME"

[ -z "$URL" ] && exit 1

cat > "$CONFIG" <<EOC
SERVER_URL=$URL
SCREEN_NAME=$NAME
WATCHDOG_CHECK_INTERVAL=30
WATCHDOG_GRACE_PERIOD=90
WATCHDOG_FAILURES_BEFORE_REBOOT=1
FIREFOX_RESTART_INTERVAL_SECONDS=21600
EOC
EOF

chmod +x "$VISIO_DIR/bootstrap.sh"

echo "==> Création kiosk.sh"
cat > "$VISIO_DIR/kiosk.sh" <<'EOF'
#!/bin/bash

set -euo pipefail

CONFIG="/etc/visio/client.conf"

extract_host() {
    echo "$1" | sed -E 's#^[a-zA-Z]+://##' | cut -d/ -f1 | cut -d: -f1
}

wait_with_ui() {
    local host="$1"
    xterm -fa Monospace -fs 14 -fullscreen -bg black -fg green -e bash -c "
spin='|/-\\\\'
i=0

clear
echo
echo 'Connexion au serveur en cours...'
echo
echo 'Serveur : $host'
echo

while true; do
    i=\$(( (i + 1) % 4 ))
    printf '\r[%c] Attente reseau...' \"\${spin:\$i:1}\"
    ping -c1 -W1 '$host' >/dev/null 2>&1 && break
    sleep 2
done

echo
sleep 1
"
}

bootstrap_ui() {
    xterm -fa Monospace -fs 14 -fullscreen -bg black -fg green -e /opt/visio/bootstrap.sh
}

error_ui() {
    local msg="$1"
    xterm -fa Monospace -fs 14 -fullscreen -bg black -fg red -e bash -c "
clear
echo
echo '$msg'
echo
read -p 'Appuie sur Entree...'
"
}

if [ ! -s "$CONFIG" ]; then
    bootstrap_ui
fi

if [ ! -s "$CONFIG" ]; then
    error_ui "Configuration absente dans /etc/visio/client.conf"
    exit 1
fi

read_conf() {
    local key="$1"
    local line=""
    line="$(grep "^${key}=" "$CONFIG" 2>/dev/null | head -n1 || true)"
    printf '%s' "${line#*=}"
}

SERVER_URL="$(read_conf SERVER_URL)"
SCREEN_NAME="$(read_conf SCREEN_NAME)"
TARGET_HOST="$(extract_host "$SERVER_URL")"

DISPLAY_URL="$(
python3 - <<'PY' "$SERVER_URL" "$SCREEN_NAME"
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import sys

raw_url = (sys.argv[1] or '').strip()
screen_name = (sys.argv[2] or '').strip()
parts = urlsplit(raw_url)
query = dict(parse_qsl(parts.query, keep_blank_values=True))
if screen_name:
    query['screen'] = screen_name
display_url = urlunsplit((
    parts.scheme,
    parts.netloc,
    parts.path or '/',
    urlencode(query),
    parts.fragment,
))
print(display_url)
PY
)"

[ -z "$SERVER_URL" ] || [ -z "$TARGET_HOST" ] && {
    error_ui "Configuration invalide dans /etc/visio/client.conf"
    exit 1
}

FIREFOX_RESTART_INTERVAL_SECONDS="$(read_conf FIREFOX_RESTART_INTERVAL_SECONDS)"
case "${FIREFOX_RESTART_INTERVAL_SECONDS:-}" in
    ''|*[!0-9]*)
        FIREFOX_RESTART_INTERVAL_SECONDS=21600
        ;;
esac
if [ "$FIREFOX_RESTART_INTERVAL_SECONDS" -lt 1800 ]; then
    FIREFOX_RESTART_INTERVAL_SECONDS=1800
fi

setup_firefox_profile() {
    local profile_dir="$HOME/.mozilla/firefox/visio-kiosk"
    mkdir -p "$profile_dir"
    cat > "$profile_dir/user.js" <<'EOP'
user_pref("app.normandy.enabled", false);
user_pref("app.shield.optoutstudies.enabled", false);
user_pref("browser.aboutConfig.showWarning", false);
user_pref("browser.bookmarks.restore_default_bookmarks", false);
user_pref("browser.cache.disk.enable", false);
user_pref("browser.discovery.enabled", false);
user_pref("browser.newtabpage.activity-stream.feeds.telemetry", false);
user_pref("browser.newtabpage.activity-stream.telemetry", false);
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.ping-centre.telemetry", false);
user_pref("browser.search.suggest.enabled", false);
user_pref("browser.sessionhistory.max_total_viewers", 0);
user_pref("browser.sessionstore.max_tabs_undo", 0);
user_pref("browser.sessionstore.max_windows_undo", 0);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.tabs.crashReporting.sendReport", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("browser.urlbar.suggest.searches", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("dom.ipc.processCount", 1);
user_pref("dom.push.enabled", false);
user_pref("dom.serviceWorkers.enabled", false);
user_pref("extensions.pocket.enabled", false);
user_pref("media.cache_readahead_limit", 60);
user_pref("media.cache_resume_threshold", 30);
user_pref("media.peerconnection.enabled", false);
user_pref("media.rdd-process.enabled", false);
user_pref("network.dns.disablePrefetch", true);
user_pref("network.prefetch-next", false);
user_pref("toolkit.cosmeticAnimations.enabled", false);
user_pref("toolkit.telemetry.archive.enabled", false);
user_pref("toolkit.telemetry.bhrPing.enabled", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.firstShutdownPing.enabled", false);
user_pref("toolkit.telemetry.newProfilePing.enabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("toolkit.telemetry.server", "");
user_pref("toolkit.telemetry.shutdownPingSender.enabled", false);
user_pref("toolkit.telemetry.unified", false);
EOP
    printf '%s\n' "$profile_dir"
}

FIREFOX_PROFILE_DIR="$(setup_firefox_profile)"

wait_with_ui "$TARGET_HOST"

pkill -x unclutter 2>/dev/null || true
unclutter -idle 0 &
openbox-session &

sleep 1
# Disable X11 screen blanking while the kiosk session is running.
xset s off
xset -dpms
xset s noblank

LOG_FILE="/tmp/visio-firefox.log"
export DISPLAY_URL LOG_FILE FIREFOX_PROFILE_DIR FIREFOX_RESTART_INTERVAL_SECONDS

# Keep the X session alive even if Firefox is killed unexpectedly.
exec systemd-inhibit \
    --what=idle:sleep:handle-lid-switch \
    --who="Visio Display" \
    --why="Kiosque d'affichage actif" \
    bash -c '
set +e
while true; do
    firefox-esr --kiosk --no-remote --profile "$FIREFOX_PROFILE_DIR" "$DISPLAY_URL" &
    firefox_pid=$!
    started_at=$(date +%s)

    while kill -0 "$firefox_pid" >/dev/null 2>&1; do
        sleep 30
        now=$(date +%s)
        if [ $((now - started_at)) -ge "$FIREFOX_RESTART_INTERVAL_SECONDS" ]; then
            printf "%s firefox-esr periodic restart after %ss\n" "$(date "+%F %T")" "$FIREFOX_RESTART_INTERVAL_SECONDS" >> "$LOG_FILE"
            kill -TERM "$firefox_pid" >/dev/null 2>&1 || true
            sleep 5
            kill -0 "$firefox_pid" >/dev/null 2>&1 && kill -KILL "$firefox_pid" >/dev/null 2>&1 || true
            break
        fi
    done

    wait "$firefox_pid"
    status=$?
    printf "%s firefox-esr exited with status %s\n" "$(date "+%F %T")" "$status" >> "$LOG_FILE"
    sleep 2
done
'
EOF

chmod +x "$VISIO_DIR/kiosk.sh"

echo "==> Création client-heartbeat.sh"
cat > "$VISIO_DIR/client-heartbeat.sh" <<'EOF'
#!/bin/bash

set -euo pipefail

CONFIG="/etc/visio/client.conf"

read_conf() {
    local key="$1"
    local line=""
    line="$(grep "^${key}=" "$CONFIG" 2>/dev/null | head -n1 || true)"
    printf '%s' "${line#*=}"
}

[ -s "$CONFIG" ] || exit 0

SERVER_URL="$(read_conf SERVER_URL)"
SCREEN_NAME="$(read_conf SCREEN_NAME)"

[ -n "$SERVER_URL" ] || exit 0

HEARTBEAT_URL="$(
python3 - <<'PY' "$SERVER_URL"
from urllib.parse import urlsplit, urlunsplit
import sys

raw = (sys.argv[1] or '').strip()
parts = urlsplit(raw)
base = urlunsplit((parts.scheme, parts.netloc, '', '', '')).rstrip('/')
print(f"{base}/api/client-heartbeat" if base else '')
PY
)"

[ -n "$HEARTBEAT_URL" ] || exit 0

HOSTNAME_VALUE="$(hostname 2>/dev/null || true)"
MACHINE_ID="$HOSTNAME_VALUE"
[ -n "$MACHINE_ID" ] || MACHINE_ID="$(cat /etc/machine-id 2>/dev/null || true)"
CLIENT_VERSION="2026.04"

payload=$(
python3 - <<'PY' "$MACHINE_ID" "$HOSTNAME_VALUE" "$SCREEN_NAME" "$SERVER_URL" "$CLIENT_VERSION"
import json
import os
import shutil
import subprocess
import sys
import time


def read_uptime_seconds():
    try:
        with open('/proc/uptime', encoding='utf-8') as handle:
            return int(float(handle.read().split()[0]))
    except Exception:
        return None


def read_cpu_load_percent():
    def sample():
        with open('/proc/stat', encoding='utf-8') as handle:
            fields = handle.readline().split()[1:]
        values = [int(field) for field in fields[:8]]
        idle = values[3] + values[4]
        total = sum(values)
        return idle, total

    try:
        idle_1, total_1 = sample()
        time.sleep(0.2)
        idle_2, total_2 = sample()
        idle_delta = idle_2 - idle_1
        total_delta = total_2 - total_1
        if total_delta <= 0:
            return None
        usage = (1 - (idle_delta / total_delta)) * 100
        return round(max(0.0, min(100.0, usage)), 1)
    except Exception:
        return None


def read_memory():
    data = {}
    try:
        with open('/proc/meminfo', encoding='utf-8') as handle:
            for line in handle:
                key, raw_value = line.split(':', 1)
                data[key] = int(raw_value.strip().split()[0])
        total_mb = data.get('MemTotal')
        available_mb = data.get('MemAvailable')
        if total_mb is None or available_mb is None:
            return None, None
        total_mb //= 1024
        used_mb = max(0, (data['MemTotal'] - data['MemAvailable']) // 1024)
        return used_mb, total_mb
    except Exception:
        return None, None


def read_temperature():
    candidates = []
    thermal_root = '/sys/class/thermal'
    try:
        for name in os.listdir(thermal_root):
            if not name.startswith('thermal_zone'):
                continue
            temp_path = os.path.join(thermal_root, name, 'temp')
            try:
                with open(temp_path, encoding='utf-8') as handle:
                    raw_value = handle.read().strip()
                if not raw_value:
                    continue
                value = float(raw_value)
                if value > 1000:
                    value /= 1000.0
                if 0 < value < 150:
                    candidates.append(value)
            except Exception:
                continue
    except Exception:
        return None
    if not candidates:
        return None
    return round(max(candidates), 1)


def read_disk():
    try:
        usage = shutil.disk_usage('/')
        total_mb = int(usage.total / (1024 * 1024))
        free_mb = int(usage.free / (1024 * 1024))
        return free_mb, total_mb
    except Exception:
        return None, None


def read_resolution():
    for path in (
        '/sys/class/graphics/fb0/virtual_size',
        '/sys/class/graphics/fb1/virtual_size',
    ):
        try:
            with open(path, encoding='utf-8') as handle:
                width, height = handle.read().strip().split(',', 1)
            if width and height:
                return f'{width}x{height}'
        except Exception:
            pass

    drm_root = '/sys/class/drm'
    try:
        for name in os.listdir(drm_root):
            modes_path = os.path.join(drm_root, name, 'modes')
            try:
                with open(modes_path, encoding='utf-8') as handle:
                    first_mode = handle.readline().strip()
                if first_mode:
                    return first_mode
            except Exception:
                continue
    except Exception:
        return ''
    return ''


def detect_last_error():
    status_path = '/run/visio/watchdog.last_error'
    try:
        with open(status_path, encoding='utf-8') as handle:
            persisted = handle.read().strip()
        if persisted:
            return persisted
    except Exception:
        pass

    try:
        result = subprocess.run(
            ['pgrep', '-f', 'firefox-esr.*--kiosk'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            return 'Kiosk browser not running'
    except Exception:
        return ''
    return ''


ram_used_mb, ram_total_mb = read_memory()
disk_free_mb, disk_total_mb = read_disk()

print(json.dumps({
    "machine_id": sys.argv[1],
    "hostname": sys.argv[2],
    "client_name": sys.argv[3] or sys.argv[2],
    "screen_name": sys.argv[3],
    "server_url": sys.argv[4],
    "client_version": sys.argv[5],
    "uptime_seconds": read_uptime_seconds(),
    "cpu_load_percent": read_cpu_load_percent(),
    "ram_used_mb": ram_used_mb,
    "ram_total_mb": ram_total_mb,
    "temperature_c": read_temperature(),
    "disk_free_mb": disk_free_mb,
    "disk_total_mb": disk_total_mb,
    "resolution": read_resolution(),
    "last_error": detect_last_error(),
}))
PY
)

curl -fsS --max-time 10 \
  -H "Content-Type: application/json" \
  -d "$payload" \
  "$HEARTBEAT_URL" >/dev/null
EOF

chmod +x "$VISIO_DIR/client-heartbeat.sh"

echo "==> Création client-watchdog.sh"
cat > "$VISIO_DIR/client-watchdog.sh" <<'EOF'
#!/bin/bash

set -euo pipefail

CONFIG="/etc/visio/client.conf"
STATE_DIR="/run/visio"
STATE_FILE="$STATE_DIR/watchdog.state"
LAST_ERROR_FILE="$STATE_DIR/watchdog.last_error"

mkdir -p "$STATE_DIR"

read_conf() {
    local key="$1"
    grep "^${key}=" "$CONFIG" 2>/dev/null | head -n1 | cut -d '=' -f2-
}

read_uptime_seconds() {
    python3 - <<'PY'
try:
    with open('/proc/uptime', encoding='utf-8') as handle:
        print(int(float(handle.read().split()[0])))
except Exception:
    print(0)
PY
}

SERVER_URL="$(read_conf SERVER_URL)"
[ -n "$SERVER_URL" ] || exit 0

POLICY_JSON="$(
python3 - <<'PY' "$SERVER_URL"
from urllib.parse import urlsplit, urlunsplit
import sys

raw = (sys.argv[1] or '').strip()
parts = urlsplit(raw)
base = urlunsplit((parts.scheme, parts.netloc, '', '', '')).rstrip('/')
print(f"{base}/api/client-policy" if base else '')
PY
)"

DEFAULT_ENABLED="$(read_conf WATCHDOG_ENABLED)"
DEFAULT_INTERVAL="$(read_conf WATCHDOG_CHECK_INTERVAL)"
DEFAULT_GRACE="$(read_conf WATCHDOG_GRACE_PERIOD)"
DEFAULT_FAILURES="$(read_conf WATCHDOG_FAILURES_BEFORE_REBOOT)"

export DEFAULT_INTERVAL DEFAULT_GRACE DEFAULT_FAILURES

POLICY_RESPONSE=""
if [ -n "$POLICY_JSON" ]; then
    POLICY_RESPONSE="$(curl -fsS --max-time 8 "$POLICY_JSON" 2>/dev/null || true)"
fi

POLICY_VARS="$(
python3 - <<'PY' "$POLICY_RESPONSE"
import json
import os
import sys

def as_bool(value, default):
    if isinstance(value, bool):
        return value
    if value in (None, ''):
        return default
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off'}

def as_int(value, default, minimum):
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default

default_interval = as_int(os.environ.get('DEFAULT_INTERVAL', '30'), 30, 15)
default_grace = as_int(os.environ.get('DEFAULT_GRACE', '90'), 90, 30)
default_failures = as_int(os.environ.get('DEFAULT_FAILURES', '1'), 1, 1)

payload = {}
try:
    raw = (sys.argv[1] or '').strip()
    if raw:
        payload = json.loads(raw).get('watchdog', {})
except Exception:
    payload = {}

interval = as_int(payload.get('check_interval_seconds'), default_interval, 15)
grace = as_int(payload.get('grace_period_seconds'), default_grace, 30)
failures = as_int(payload.get('consecutive_failures_before_reboot'), default_failures, 1)

print(f"CHECK_INTERVAL={interval}")
print(f"GRACE_PERIOD={grace}")
print(f"FAILURES_BEFORE_REBOOT={failures}")
PY
)"

eval "$POLICY_VARS"

mkdir -p "$STATE_DIR"
touch "$STATE_FILE"

LAST_CHECK_TS=0
FAILURES=0
if [ -f "$STATE_FILE" ]; then
    # shellcheck disable=SC1090
    . "$STATE_FILE" || true
fi

NOW_TS="$(date +%s)"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"
GRACE_PERIOD="${GRACE_PERIOD:-90}"
FAILURES_BEFORE_REBOOT="${FAILURES_BEFORE_REBOOT:-1}"

if [ $((NOW_TS - LAST_CHECK_TS)) -lt "$CHECK_INTERVAL" ]; then
    exit 0
fi

UPTIME_SECONDS="$(read_uptime_seconds)"
if [ "$UPTIME_SECONDS" -lt "$GRACE_PERIOD" ]; then
    cat > "$STATE_FILE" <<EOC
LAST_CHECK_TS=$NOW_TS
FAILURES=0
EOC
    : > "$LAST_ERROR_FILE"
    exit 0
fi

if pgrep -f 'firefox-esr.*--kiosk' >/dev/null 2>&1; then
    cat > "$STATE_FILE" <<EOC
LAST_CHECK_TS=$NOW_TS
FAILURES=0
EOC
    : > "$LAST_ERROR_FILE"
    exit 0
fi

FAILURES=$((FAILURES + 1))
MESSAGE="Kiosk browser not running (${FAILURES}/${FAILURES_BEFORE_REBOOT})"

cat > "$STATE_FILE" <<EOC
LAST_CHECK_TS=$NOW_TS
FAILURES=$FAILURES
EOC
printf '%s' "$MESSAGE" > "$LAST_ERROR_FILE"

[ "$FAILURES" -lt "$FAILURES_BEFORE_REBOOT" ] || {
    printf '%s - reboot scheduled' "$MESSAGE" > "$LAST_ERROR_FILE"
    sync || true
    systemctl reboot
}
EOF

chmod +x "$VISIO_DIR/client-watchdog.sh"

echo "==> Création .xinitrc"
cat > "$USER_HOME/.xinitrc" <<'EOF'
#!/bin/bash
exec /opt/visio/kiosk.sh
EOF
chmod +x "$USER_HOME/.xinitrc"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.xinitrc"

echo "==> Création .bash_profile"
cat > "$USER_HOME/.bash_profile" <<'EOF'
if [ -z "$DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    startx
fi
EOF
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.bash_profile"

echo "==> Activation autologin tty1"
cat > /etc/systemd/system/getty@tty1.service.d/override.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER_NAME --noclear %I \$TERM
Type=idle
EOF

echo "==> Service premier reboot"
cat > /etc/systemd/system/visio-firstboot.service <<'EOF'
[Unit]
Description=Premier reboot apres installation Visio
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c '/bin/systemctl disable visio-firstboot.service; rm -f /etc/systemd/system/visio-firstboot.service; /bin/systemctl daemon-reload; sleep 3; /bin/systemctl reboot'

[Install]
WantedBy=multi-user.target
EOF

echo "==> Service heartbeat client"
cat > /etc/systemd/system/visio-client-heartbeat.service <<'EOF'
[Unit]
Description=Heartbeat du client Visio vers le serveur
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/visio/client-heartbeat.sh
EOF

cat > /etc/systemd/system/visio-client-heartbeat.timer <<'EOF'
[Unit]
Description=Envoi periodique du heartbeat client Visio

[Timer]
OnBootSec=15
OnUnitActiveSec=30
Unit=visio-client-heartbeat.service

[Install]
WantedBy=timers.target
EOF

echo "==> Service watchdog client"
cat > /etc/systemd/system/visio-client-watchdog.service <<'EOF'
[Unit]
Description=Surveillance du kiosque Visio
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/opt/visio/client-watchdog.sh
EOF

cat > /etc/systemd/system/visio-client-watchdog.timer <<'EOF'
[Unit]
Description=Verification periodique du kiosque Visio

[Timer]
OnBootSec=45
OnUnitActiveSec=30
Unit=visio-client-watchdog.service

[Install]
WantedBy=timers.target
EOF

/bin/systemctl daemon-reload
/bin/systemctl enable visio-firstboot.service
/bin/systemctl enable --now visio-client-heartbeat.timer
/bin/systemctl start visio-client-heartbeat.service || true
/bin/systemctl enable --now visio-client-watchdog.timer
/bin/systemctl start visio-client-watchdog.service || true

echo "Installation terminée."
echo "Utilisateur configuré : $USER_NAME"
if [ "$AUTO_REBOOT" -eq 1 ]; then
    echo "Redémarrage automatique dans 3 secondes..."
    sleep 3
    /bin/systemctl reboot
else
    echo "Redémarrage automatique désactivé (--no-reboot)."
fi
