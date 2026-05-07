#!/bin/bash
# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -euo pipefail

REPO_URL="https://github.com/woofix/visio_display.git"
DEFAULT_INSTALL_DIR="$(pwd)/visio_display"
DEFAULT_PORT="8081"

# ── Colors ────────────────────────────────────────────────────────────────────
BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

header() { echo -e "\n${CYAN}${BOLD}==> $1${NC}"; }
ok()     { echo -e "${GREEN}✓ $1${NC}"; }
warn()   { echo -e "${YELLOW}⚠ $1${NC}"; }
die()    { echo -e "${RED}✗ $1${NC}" >&2; exit 1; }

# ── Prerequisites ─────────────────────────────────────────────────────────────
header "Checking prerequisites"

command -v docker  >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || die "Docker Compose (plugin v2) is not installed."
command -v git     >/dev/null 2>&1 || die "git is not installed (apt install git)."

ok "Docker, Docker Compose and git are available."

# ── Installation directory ────────────────────────────────────────────────────
header "Installation directory"
read -rp "Installation directory [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

if [ -d "$INSTALL_DIR/.git" ]; then
    die "The directory $INSTALL_DIR already contains a Git repository. Choose another directory."
elif [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    die "The directory $INSTALL_DIR exists and is not empty. Choose another directory."
else
    header "Cloning repository"
    git clone --branch main "$REPO_URL" "$INSTALL_DIR"
    ok "Repository cloned into $INSTALL_DIR."
fi

cd "$INSTALL_DIR"

# ── Administrator account ─────────────────────────────────────────────────────
header "Creating administrator account"

while true; do
    read -rp "Admin username: " ADMIN_USER
    [[ -n "$ADMIN_USER" && "$ADMIN_USER" =~ ^[a-zA-Z0-9_.-]+$ ]] && break
    warn "Invalid name. Use only letters, digits, hyphens and dots."
done

while true; do
    read -srp "Admin password: " ADMIN_PASSWORD; echo
    [[ ${#ADMIN_PASSWORD} -ge 10 ]] || { warn "Password must be at least 10 characters."; continue; }
    read -srp "Confirm password: " ADMIN_PASSWORD2; echo
    [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD2" ]] && break
    warn "Passwords do not match."
done

ok "Admin account configured: $ADMIN_USER"

# ── Port ──────────────────────────────────────────────────────────────────────
header "Network configuration"
read -rp "Server HTTP port [${DEFAULT_PORT}]: " PORT
PORT="${PORT:-$DEFAULT_PORT}"

# ── Clean existing data ───────────────────────────────────────────────────────
header "Cleanup"

warn "This step will stop the containers and delete all existing data (database, cache)."
read -rp "Press Enter to continue or Ctrl+C to cancel..."

PROJECT_NAME="$(basename "$INSTALL_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
docker compose down --remove-orphans 2>/dev/null || true
for vol in postgres_data redis_data; do
    VNAME="${PROJECT_NAME}_${vol}"
    if docker volume inspect "$VNAME" >/dev/null 2>&1; then
        docker volume rm "$VNAME" >/dev/null
        ok "Volume $VNAME removed."
    fi
done

# ── PostgreSQL password ───────────────────────────────────────────────────────
header "PostgreSQL database"

while true; do
    read -srp "PostgreSQL password: " POSTGRES_PASSWORD; echo
    [[ ${#POSTGRES_PASSWORD} -ge 10 ]] || { warn "Password must be at least 10 characters."; continue; }
    read -srp "Confirm password: " POSTGRES_PASSWORD2; echo
    [[ "$POSTGRES_PASSWORD" == "$POSTGRES_PASSWORD2" ]] && break
    warn "Passwords do not match."
done

ok "PostgreSQL password configured."

# ── Flask secret key ──────────────────────────────────────────────────────────
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null \
    || openssl rand -hex 32)"

# ── Data directories ──────────────────────────────────────────────────────────
header "Data directories"

MEDIA_DIR_DEFAULT="$INSTALL_DIR/media"
PRIVATE_DIR_DEFAULT="$INSTALL_DIR/private"

read -rp "Media directory [${MEDIA_DIR_DEFAULT}]: " MEDIA_DIR
MEDIA_DIR="${MEDIA_DIR:-$MEDIA_DIR_DEFAULT}"

read -rp "Private data directory [${PRIVATE_DIR_DEFAULT}]: " PRIVATE_DIR
PRIVATE_DIR="${PRIVATE_DIR:-$PRIVATE_DIR_DEFAULT}"

mkdir -p "$MEDIA_DIR" "$PRIVATE_DIR"
ok "Directories created."

# ── .env file ─────────────────────────────────────────────────────────────────
header "Generating .env file"

if [ -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak"
    warn "Previous .env saved to .env.bak"
fi

cat > "$INSTALL_DIR/.env" <<EOF
ADMIN_USER=${ADMIN_USER}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
SECRET_KEY=${SECRET_KEY}
PORT=${PORT}
MEDIA_DIR=${MEDIA_DIR}
PRIVATE_DIR=${PRIVATE_DIR}
POSTGRES_USER=visio
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=visio
EOF

chmod 600 "$INSTALL_DIR/.env"
ok ".env file generated."

# ── Security hardening ────────────────────────────────────────────────────────
header "Security hardening"
bash ./scripts/security_bootstrap.sh install "$INSTALL_DIR"

# ── Launch ────────────────────────────────────────────────────────────────────
header "Starting containers"

cd "$INSTALL_DIR"
docker compose pull --quiet 2>/dev/null || true
docker compose up -d --build

ok "Containers started."

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo -e "${BOLD}  Installation complete!${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo
echo -e "  URL        : ${CYAN}http://$(hostname -I | awk '{print $1}'):${PORT}${NC}"
echo -e "  Admin      : ${BOLD}${ADMIN_USER}${NC}"
echo -e "  Media      : ${MEDIA_DIR}"
echo -e "  Data       : ${PRIVATE_DIR}"
echo
echo -e "  ${YELLOW}Keep your .env file in a safe place.${NC}"
echo
