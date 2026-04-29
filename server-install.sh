#!/bin/bash
# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -euo pipefail

REPO_URL="https://github.com/woofix/visio_display.git"
DEFAULT_INSTALL_DIR="$(pwd)/visio_display"
DEFAULT_PORT="8081"
RUN_UPDATE=0

# ── Couleurs ──────────────────────────────────────────────────────────────────
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

# ── Vérifications préalables ──────────────────────────────────────────────────
header "Vérification des prérequis"

command -v docker  >/dev/null 2>&1 || die "Docker n'est pas installé. Voir https://docs.docker.com/engine/install/"
docker compose version >/dev/null 2>&1 || die "Docker Compose (plugin v2) n'est pas installé."
command -v git     >/dev/null 2>&1 || die "git n'est pas installé (apt install git)."

ok "Docker, Docker Compose et git sont disponibles."

# ── Dossier d'installation ────────────────────────────────────────────────────
header "Dossier d'installation"
read -rp "Dossier d'installation [${DEFAULT_INSTALL_DIR}] : " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

if [ -d "$INSTALL_DIR/.git" ]; then
    warn "Le dossier $INSTALL_DIR contient déjà un dépôt Git."
    read -rp "Mettre à jour le dépôt existant ? [o/N] : " UPDATE_EXISTING
    if [[ "$UPDATE_EXISTING" =~ ^[oOyY]$ ]]; then
        git -C "$INSTALL_DIR" pull --ff-only
        ok "Dépôt mis à jour."
        RUN_UPDATE=1
    fi
elif [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    die "Le dossier $INSTALL_DIR existe et n'est pas vide. Choisissez un autre dossier."
else
    header "Clonage du dépôt"
    git clone "$REPO_URL" "$INSTALL_DIR"
    ok "Dépôt cloné dans $INSTALL_DIR."
fi

cd "$INSTALL_DIR"

if [ "$RUN_UPDATE" -eq 1 ]; then
    header "Durcissement sécurité"
    bash ./scripts/security_bootstrap.sh update "$INSTALL_DIR"
    docker compose pull --quiet 2>/dev/null || true
    docker compose up -d --build
    ok "Mise à jour terminée sans remplacer les secrets existants."
    exit 0
fi

# ── Compte administrateur ─────────────────────────────────────────────────────
header "Création du compte administrateur"

while true; do
    read -rp "Nom d'utilisateur admin : " ADMIN_USER
    [[ -n "$ADMIN_USER" && "$ADMIN_USER" =~ ^[a-zA-Z0-9_.-]+$ ]] && break
    warn "Nom invalide. Utilisez uniquement lettres, chiffres, tirets et points."
done

while true; do
    read -srp "Mot de passe admin : " ADMIN_PASSWORD; echo
    [[ ${#ADMIN_PASSWORD} -ge 10 ]] || { warn "Le mot de passe doit faire au moins 10 caractères."; continue; }
    read -srp "Confirmer le mot de passe : " ADMIN_PASSWORD2; echo
    [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD2" ]] && break
    warn "Les mots de passe ne correspondent pas."
done

ok "Compte admin configuré : $ADMIN_USER"

# ── Port ──────────────────────────────────────────────────────────────────────
header "Configuration réseau"
read -rp "Port HTTP du serveur [${DEFAULT_PORT}] : " PORT
PORT="${PORT:-$DEFAULT_PORT}"

# ── Nettoyage des données existantes ─────────────────────────────────────────
header "Nettoyage"

warn "Cette étape va arrêter les containers et supprimer toutes les données existantes (base de données, cache)."
read -rp "Appuyez sur Entrée pour continuer ou Ctrl+C pour annuler..."

PROJECT_NAME="$(basename "$INSTALL_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
docker compose down --remove-orphans 2>/dev/null || true
for vol in postgres_data redis_data; do
    VNAME="${PROJECT_NAME}_${vol}"
    if docker volume inspect "$VNAME" >/dev/null 2>&1; then
        docker volume rm "$VNAME" >/dev/null
        ok "Volume $VNAME supprimé."
    fi
done

# ── Mot de passe PostgreSQL ───────────────────────────────────────────────────
header "Base de données PostgreSQL"

while true; do
    read -srp "Mot de passe PostgreSQL : " POSTGRES_PASSWORD; echo
    [[ ${#POSTGRES_PASSWORD} -ge 10 ]] || { warn "Le mot de passe doit faire au moins 10 caractères."; continue; }
    read -srp "Confirmer le mot de passe : " POSTGRES_PASSWORD2; echo
    [[ "$POSTGRES_PASSWORD" == "$POSTGRES_PASSWORD2" ]] && break
    warn "Les mots de passe ne correspondent pas."
done

ok "Mot de passe PostgreSQL configuré."

# ── Clé secrète Flask ─────────────────────────────────────────────────────────
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null \
    || openssl rand -hex 32)"

# ── Dossiers de données ───────────────────────────────────────────────────────
header "Dossiers de données"

MEDIA_DIR_DEFAULT="$INSTALL_DIR/web/static/data"
PRIVATE_DIR_DEFAULT="$INSTALL_DIR/web/data/private"

read -rp "Dossier des médias [${MEDIA_DIR_DEFAULT}] : " MEDIA_DIR
MEDIA_DIR="${MEDIA_DIR:-$MEDIA_DIR_DEFAULT}"

read -rp "Dossier des données privées [${PRIVATE_DIR_DEFAULT}] : " PRIVATE_DIR
PRIVATE_DIR="${PRIVATE_DIR:-$PRIVATE_DIR_DEFAULT}"

mkdir -p "$MEDIA_DIR" "$PRIVATE_DIR"
ok "Dossiers créés."

# ── Fichier .env ──────────────────────────────────────────────────────────────
header "Génération du fichier .env"

if [ -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak"
    warn "Ancien .env sauvegardé dans .env.bak"
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
ok "Fichier .env généré."

# ── Durcissement sécurité ─────────────────────────────────────────────────────
header "Durcissement sécurité"
bash ./scripts/security_bootstrap.sh install "$INSTALL_DIR"

# ── Lancement ─────────────────────────────────────────────────────────────────
header "Lancement des containers"

cd "$INSTALL_DIR"
docker compose pull --quiet 2>/dev/null || true
docker compose up -d --build

ok "Containers démarrés."

# ── Résumé ────────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo -e "${BOLD}  Installation terminée !${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo
echo -e "  URL        : ${CYAN}http://$(hostname -I | awk '{print $1}'):${PORT}${NC}"
echo -e "  Admin      : ${BOLD}${ADMIN_USER}${NC}"
echo -e "  Médias     : ${MEDIA_DIR}"
echo -e "  Données    : ${PRIVATE_DIR}"
echo
echo -e "  ${YELLOW}Conservez votre fichier .env en lieu sûr.${NC}"
echo
