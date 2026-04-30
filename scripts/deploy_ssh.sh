#!/bin/sh

# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

set -eu

usage() {
    cat <<'EOF'
Usage: scripts/deploy_ssh.sh [options]

Deploy Visio-Display to a remote server over SSH, then restart docker compose.

Options:
  --profile NAME         Load a saved server profile
  --host HOST            SSH host or IP
  --user USER            SSH user
  --port PORT            SSH port (default: 22)
  --remote-dir DIR       Remote project directory (default: /opt/visio_display)
  --app-service NAME     Main docker compose service to wait for (default: app)
  --compose-file PATH    Remote compose file path relative to remote-dir (default: docker-compose.yml)
  --skip-build           Run 'docker compose up -d' without '--build'
  --no-prune             Do not pass '--remove-orphans'
  --no-wait              Do not wait for the app container health/status
  --save-profile NAME    Save or update the server profile before deploying
  --list-profiles        Show saved server profiles and exit
  --password-auth        Force SSH password prompt instead of SSH key mode
  --help                 Show this help

Environment fallbacks:
  VISIO_DEPLOY_PROFILE
  VISIO_DEPLOY_HOST
  VISIO_DEPLOY_USER
  VISIO_DEPLOY_PORT
  VISIO_DEPLOY_REMOTE_DIR
EOF
}

PROFILE_NAME="${VISIO_DEPLOY_PROFILE:-}"
HOST="${VISIO_DEPLOY_HOST:-}"
USER_NAME="${VISIO_DEPLOY_USER:-}"
PORT="${VISIO_DEPLOY_PORT:-22}"
REMOTE_DIR="${VISIO_DEPLOY_REMOTE_DIR:-/opt/visio_display}"
APP_SERVICE="app"
COMPOSE_FILE="docker-compose.yml"
BUILD_FLAG="--build"
PRUNE_FLAG="--remove-orphans"
WAIT_FOR_APP=1
SAVE_PROFILE_NAME=""
PASSWORD_AUTH=0

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}/visio_display"
SERVER_STORE="$CONFIG_HOME/deploy_ssh_servers.tsv"

ensure_store_dir() {
    mkdir -p "$CONFIG_HOME"
    touch "$SERVER_STORE"
}

trim() {
    printf '%s' "$1" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

profile_exists() {
    [ -f "$SERVER_STORE" ] && awk -F '\t' -v name="$1" '$1 == name { found = 1; exit } END { exit(found ? 0 : 1) }' "$SERVER_STORE"
}

load_profile() {
    name="$1"
    if ! profile_exists "$name"; then
        echo "Profile not found: $name" >&2
        exit 1
    fi
    line="$(awk -F '\t' -v name="$name" '$1 == name { printf "%s\t%s\t%s\t%s\t%s\n", $2, $3, $4, $5, $6; exit }' "$SERVER_STORE")"
    old_ifs=$IFS
    IFS='	'
    set -- $line
    IFS=$old_ifs
    HOST="${1:-$HOST}"
    USER_NAME="${2:-$USER_NAME}"
    PORT="${3:-$PORT}"
    REMOTE_DIR="${4:-$REMOTE_DIR}"
    if [ "${5:-0}" = "1" ]; then
        PASSWORD_AUTH=1
    fi
    PROFILE_NAME="$name"
}

save_profile() {
    name="$1"
    ensure_store_dir
    tmp_file="$(mktemp)"
    awk -F '\t' -v OFS='\t' \
        -v name="$name" \
        -v host="$HOST" \
        -v user="$USER_NAME" \
        -v port="$PORT" \
        -v remote="$REMOTE_DIR" \
        -v password_auth="$PASSWORD_AUTH" '
        BEGIN { updated = 0 }
        $1 == name {
            print name, host, user, port, remote, password_auth
            updated = 1
            next
        }
        { print $0 }
        END {
            if (updated == 0) {
                print name, host, user, port, remote, password_auth
            }
        }
    ' "$SERVER_STORE" > "$tmp_file"
    mv "$tmp_file" "$SERVER_STORE"
}

list_profiles() {
    ensure_store_dir
    if ! [ -s "$SERVER_STORE" ]; then
        echo "No saved profiles."
        exit 0
    fi
    awk -F '\t' '{ printf "%d) %s -> %s@%s:%s %s%s\n", NR, $1, $3, $2, $4, $5, ($6 == "1" ? " [password]" : "") }' "$SERVER_STORE"
    exit 0
}

prompt_value() {
    label="$1"
    default_value="${2:-}"
    if [ -n "$default_value" ]; then
        printf "%s [%s]: " "$label" "$default_value" >&2
    else
        printf "%s: " "$label" >&2
    fi
    IFS= read -r answer || exit 1
    answer="$(trim "$answer")"
    if [ -n "$answer" ]; then
        printf '%s' "$answer"
    else
        printf '%s' "$default_value"
    fi
}

interactive_select_profile() {
    ensure_store_dir
    if [ -s "$SERVER_STORE" ]; then
        echo "Saved servers:" >&2
        awk -F '\t' '{ printf "  %d) %s -> %s@%s:%s %s%s\n", NR, $1, $3, $2, $4, $5, ($6 == "1" ? " [password]" : "") }' "$SERVER_STORE" >&2
        printf "Choose a profile (number) or press Enter to create a new one: " >&2
        IFS= read -r choice || exit 1
        choice="$(trim "$choice")"
        if [ -n "$choice" ]; then
            line="$(awk -F '\t' -v idx="$choice" 'NR == idx { printf "%s\t%s\t%s\t%s\t%s\t%s\n", $1, $2, $3, $4, $5, $6; exit }' "$SERVER_STORE")"
            if [ -z "$line" ]; then
                echo "Invalid selection." >&2
                exit 1
            fi
            old_ifs=$IFS
            IFS='	'
            set -- $line
            IFS=$old_ifs
            PROFILE_NAME="${1:-}"
            HOST="${2:-$HOST}"
            USER_NAME="${3:-$USER_NAME}"
            PORT="${4:-$PORT}"
            REMOTE_DIR="${5:-$REMOTE_DIR}"
            if [ "${6:-0}" = "1" ]; then
                PASSWORD_AUTH=1
            fi
            return
        fi
    fi

    HOST="$(prompt_value "SSH host" "$HOST")"
    USER_NAME="$(prompt_value "SSH user" "$USER_NAME")"
    PORT="$(prompt_value "SSH port" "$PORT")"
    REMOTE_DIR="$(prompt_value "Remote directory" "$REMOTE_DIR")"
    password_answer="$(prompt_value "SSH password authentication? (y/N)" "")"
    case "$password_answer" in
        y|Y|yes|Yes)
            PASSWORD_AUTH=1
            ;;
        *)
            PASSWORD_AUTH=0
            ;;
    esac

    save_answer="$(prompt_value "Save this server? (y/N)" "")"
    case "$save_answer" in
        y|Y|yes|Yes)
            profile_answer="$(prompt_value "Profile name" "$HOST")"
            if [ -n "$profile_answer" ]; then
                SAVE_PROFILE_NAME="$profile_answer"
                PROFILE_NAME="$profile_answer"
            fi
            ;;
    esac
}

validate_required_values() {
    if [ -z "$HOST" ] || [ -z "$USER_NAME" ]; then
        echo "SSH host and user are required." >&2
        exit 1
    fi
}

while [ $# -gt 0 ]; do
    case "$1" in
        --profile)
            shift
            PROFILE_NAME="${1:-}"
            ;;
        --profile=*)
            PROFILE_NAME="${1#*=}"
            ;;
        --host)
            shift
            HOST="${1:-}"
            ;;
        --host=*)
            HOST="${1#*=}"
            ;;
        --user)
            shift
            USER_NAME="${1:-}"
            ;;
        --user=*)
            USER_NAME="${1#*=}"
            ;;
        --port)
            shift
            PORT="${1:-}"
            ;;
        --port=*)
            PORT="${1#*=}"
            ;;
        --remote-dir)
            shift
            REMOTE_DIR="${1:-}"
            ;;
        --remote-dir=*)
            REMOTE_DIR="${1#*=}"
            ;;
        --app-service)
            shift
            APP_SERVICE="${1:-}"
            ;;
        --app-service=*)
            APP_SERVICE="${1#*=}"
            ;;
        --compose-file)
            shift
            COMPOSE_FILE="${1:-}"
            ;;
        --compose-file=*)
            COMPOSE_FILE="${1#*=}"
            ;;
        --skip-build)
            BUILD_FLAG=""
            ;;
        --no-prune)
            PRUNE_FLAG=""
            ;;
        --no-wait)
            WAIT_FOR_APP=0
            ;;
        --save-profile)
            shift
            SAVE_PROFILE_NAME="${1:-}"
            ;;
        --save-profile=*)
            SAVE_PROFILE_NAME="${1#*=}"
            ;;
        --password-auth)
            PASSWORD_AUTH=1
            ;;
        --list-profiles)
            list_profiles
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
    shift
done

ensure_store_dir

if [ -n "$PROFILE_NAME" ]; then
    load_profile "$PROFILE_NAME"
fi

if [ -z "$HOST" ] || [ -z "$USER_NAME" ]; then
    if [ -t 0 ]; then
        interactive_select_profile
    else
        echo "SSH host and user are required. Use --host/--user or a saved profile." >&2
        usage >&2
        exit 1
    fi
fi

validate_required_values

if [ -n "$SAVE_PROFILE_NAME" ]; then
    save_profile "$SAVE_PROFILE_NAME"
    echo "Profile saved: $SAVE_PROFILE_NAME" >&2
fi

if ! command -v ssh >/dev/null 2>&1; then
    echo "Missing command: ssh" >&2
    exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
    echo "Missing command: rsync" >&2
    exit 1
fi

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
TARGET="$USER_NAME@$HOST"
SSH_OPTS="-p $PORT -o StrictHostKeyChecking=accept-new"
if [ "$PASSWORD_AUTH" -eq 1 ]; then
    SSH_OPTS="$SSH_OPTS -o BatchMode=no"
else
    SSH_OPTS="$SSH_OPTS -o BatchMode=yes"
fi

echo "==> Checking SSH server"
ssh $SSH_OPTS "$TARGET" "mkdir -p '$REMOTE_DIR'"

echo "==> Syncing files"
rsync -az --delete \
  -e "ssh $SSH_OPTS" \
  --exclude ".git/" \
  --exclude ".github/" \
  --exclude ".venv/" \
  --exclude ".claude/" \
  --exclude "__pycache__/" \
  --exclude ".mypy_cache/" \
  --exclude ".pytest_cache/" \
  --exclude ".DS_Store" \
  --exclude ".env" \
  --exclude "data/" \
  --exclude "visio_media/" \
  --exclude "visio_private/" \
  "$PROJECT_DIR/" "$TARGET:$REMOTE_DIR/"

REMOTE_CMD=$(cat <<EOF
set -eu
cd '$REMOTE_DIR'
if ! command -v docker >/dev/null 2>&1; then
    echo "Docker not found on the server." >&2
    exit 1
fi
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD='docker compose'
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD='docker-compose'
else
    echo "Docker Compose not found on the server." >&2
    exit 1
fi
\$COMPOSE_CMD -f '$COMPOSE_FILE' up -d $BUILD_FLAG $PRUNE_FLAG
EOF
)

echo "==> Restarting remote application"
ssh $SSH_OPTS "$TARGET" "$REMOTE_CMD"

if [ "$WAIT_FOR_APP" -eq 1 ]; then
    WAIT_CMD=$(cat <<EOF
set -eu
cd '$REMOTE_DIR'
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD='docker compose'
else
    COMPOSE_CMD='docker-compose'
fi
cid=\$(\$COMPOSE_CMD -f '$COMPOSE_FILE' ps -q '$APP_SERVICE')
if [ -z "\$cid" ]; then
    echo "Service $APP_SERVICE not found." >&2
    exit 1
fi
for _ in \$(seq 1 30); do
    status=\$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "\$cid" 2>/dev/null || true)
    if [ "\$status" = "healthy" ] || [ "\$status" = "running" ]; then
        echo "Service $APP_SERVICE ready (\$status)."
        exit 0
    fi
    sleep 2
done
echo "Service $APP_SERVICE did not become ready in time." >&2
docker inspect --format '{{json .State}}' "\$cid" || true
exit 1
EOF
)
    echo "==> Checking remote service"
    ssh $SSH_OPTS "$TARGET" "$WAIT_CMD"
fi

echo "Deployment complete: $TARGET:$REMOTE_DIR"
