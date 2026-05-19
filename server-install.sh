#!/bin/bash
# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -euo pipefail

REPO_URL="https://github.com/woofix/visio_display.git"
DEFAULT_INSTALL_DIR="$(pwd)/visio_display"
DEFAULT_PORT="8081"
DEFAULT_UPDATE_BRANCH="main"
REQUESTED_MODE="${1:-}"

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

INSTALL_LANG="${VISIO_INSTALL_LANG:-}"
while [[ "$INSTALL_LANG" != "fr" && "$INSTALL_LANG" != "us" ]]; do
    read -rp "Langue / Language [fr/us]: " INSTALL_LANG
    INSTALL_LANG="${INSTALL_LANG:-fr}"
    INSTALL_LANG="$(echo "$INSTALL_LANG" | tr '[:upper:]' '[:lower:]')"
done

msg() {
    key="$1"
    case "$INSTALL_LANG:$key" in
        fr:secret_generation_failed) echo "Impossible de générer les secrets : installez python3 ou openssl." ;;
        us:secret_generation_failed) echo "Cannot generate secrets: install python3 or openssl." ;;
        fr:mode_header) echo "Mode d'exécution" ;;
        us:mode_header) echo "Run mode" ;;
        fr:mode_prompt) echo "Que voulez-vous faire ? [1=nouvelle installation, 2=mise à jour]" ;;
        us:mode_prompt) echo "What do you want to do? [1=new installation, 2=update]" ;;
        fr:invalid_mode) echo "Choix invalide. Répondez 1/install ou 2/update." ;;
        us:invalid_mode) echo "Invalid choice. Use 1/install or 2/update." ;;
        fr:mode_install) echo "Nouvelle installation" ;;
        us:mode_install) echo "New installation" ;;
        fr:mode_update) echo "Mise à jour" ;;
        us:mode_update) echo "Update" ;;
        fr:checking_prerequisites) echo "Vérification des prérequis" ;;
        us:checking_prerequisites) echo "Checking prerequisites" ;;
        fr:docker_missing) echo "Docker n'est pas installé. Voir https://docs.docker.com/engine/install/" ;;
        us:docker_missing) echo "Docker is not installed. See https://docs.docker.com/engine/install/" ;;
        fr:compose_missing) echo "Docker Compose (plugin v2) n'est pas installé." ;;
        us:compose_missing) echo "Docker Compose (plugin v2) is not installed." ;;
        fr:git_missing) echo "git n'est pas installé (apt install git)." ;;
        us:git_missing) echo "git is not installed (apt install git)." ;;
        fr:prerequisites_ok) echo "Docker, Docker Compose et git sont disponibles." ;;
        us:prerequisites_ok) echo "Docker, Docker Compose and git are available." ;;
        fr:install_dir_header) echo "Dossier d'installation" ;;
        us:install_dir_header) echo "Installation directory" ;;
        fr:install_dir_prompt) echo "Dossier d'installation" ;;
        us:install_dir_prompt) echo "Installation directory" ;;
        fr:update_dir_prompt) echo "Dossier de l'installation existante" ;;
        us:update_dir_prompt) echo "Existing installation directory" ;;
        fr:update_dir_missing) echo "Le dossier d'installation existante est introuvable." ;;
        us:update_dir_missing) echo "Existing installation directory not found." ;;
        fr:update_dir_invalid) echo "Le dossier existe mais ne semble pas être une installation Visio-Display. Aucune modification effectuée." ;;
        us:update_dir_invalid) echo "The directory exists but does not look like a Visio-Display installation. No changes were made." ;;
        fr:update_dir_not_writable) echo "Le dossier d'installation n'est pas accessible en écriture avec cet utilisateur. Corrigez les droits ou relancez avec l'utilisateur propriétaire de l'installation." ;;
        us:update_dir_not_writable) echo "The installation directory is not writable by this user. Fix ownership/permissions or rerun as the installation owner." ;;
        fr:git_dir_exists) echo "Le dossier contient déjà un dépôt Git. Choisissez un autre dossier." ;;
        us:git_dir_exists) echo "The directory already contains a Git repository. Choose another directory." ;;
        fr:dir_not_empty) echo "Le dossier existe et n'est pas vide. Choisissez un autre dossier." ;;
        us:dir_not_empty) echo "The directory exists and is not empty. Choose another directory." ;;
        fr:cloning_repository) echo "Clonage du dépôt" ;;
        us:cloning_repository) echo "Cloning repository" ;;
        fr:repository_cloned) echo "Dépôt cloné dans" ;;
        us:repository_cloned) echo "Repository cloned into" ;;
        fr:admin_header) echo "Création du compte administrateur" ;;
        us:admin_header) echo "Creating administrator account" ;;
        fr:admin_user_prompt) echo "Identifiant admin" ;;
        us:admin_user_prompt) echo "Admin username" ;;
        fr:invalid_admin_name) echo "Nom invalide. Utilisez uniquement lettres, chiffres, tirets, underscores et points." ;;
        us:invalid_admin_name) echo "Invalid name. Use only letters, digits, hyphens, underscores and dots." ;;
        fr:admin_password_prompt) echo "Mot de passe admin" ;;
        us:admin_password_prompt) echo "Admin password" ;;
        fr:password_too_short) echo "Le mot de passe doit contenir au moins 10 caractères." ;;
        us:password_too_short) echo "Password must be at least 10 characters." ;;
        fr:confirm_password_prompt) echo "Confirmer le mot de passe" ;;
        us:confirm_password_prompt) echo "Confirm password" ;;
        fr:passwords_mismatch) echo "Les mots de passe ne correspondent pas." ;;
        us:passwords_mismatch) echo "Passwords do not match." ;;
        fr:admin_configured) echo "Compte admin configuré" ;;
        us:admin_configured) echo "Admin account configured" ;;
        fr:network_header) echo "Configuration réseau" ;;
        us:network_header) echo "Network configuration" ;;
        fr:port_prompt) echo "Port HTTP du serveur" ;;
        us:port_prompt) echo "Server HTTP port" ;;
        fr:cleanup_header) echo "Nettoyage" ;;
        us:cleanup_header) echo "Cleanup" ;;
        fr:cleanup_warning) echo "Cette étape arrête les conteneurs et supprime les données existantes (base, cache)." ;;
        us:cleanup_warning) echo "This step will stop the containers and delete all existing data (database, cache)." ;;
        fr:continue_prompt) echo "Appuyez sur Entrée pour continuer ou Ctrl+C pour annuler..." ;;
        us:continue_prompt) echo "Press Enter to continue or Ctrl+C to cancel..." ;;
        fr:volume_removed) echo "Volume supprimé" ;;
        us:volume_removed) echo "Volume removed" ;;
        fr:postgres_header) echo "Base PostgreSQL" ;;
        us:postgres_header) echo "PostgreSQL database" ;;
        fr:postgres_password_prompt) echo "Mot de passe PostgreSQL" ;;
        us:postgres_password_prompt) echo "PostgreSQL password" ;;
        fr:postgres_configured) echo "Mot de passe PostgreSQL configuré." ;;
        us:postgres_configured) echo "PostgreSQL password configured." ;;
        fr:pexels_header) echo "API Pexels" ;;
        us:pexels_header) echo "Pexels API" ;;
        fr:pexels_help_1) echo "La clé Pexels est optionnelle, mais elle est nécessaire pour proposer automatiquement des images dans les annonces et les menus." ;;
        us:pexels_help_1) echo "The Pexels key is optional, but it is required to automatically suggest images in announcements and menus." ;;
        fr:pexels_help_2) echo "Pour la créer : ouvrez https://www.pexels.com/api/, connectez-vous ou créez un compte, cliquez sur « Get Started » / « Your API Key », créez une application, puis copiez la clé fournie." ;;
        us:pexels_help_2) echo "To create one: open https://www.pexels.com/api/, sign in or create an account, click \"Get Started\" / \"Your API Key\", create an application, then copy the provided key." ;;
        fr:pexels_help_3) echo "Vous pouvez laisser vide et ajouter plus tard PEXELS_API_KEY dans le fichier .env, puis redémarrer les conteneurs." ;;
        us:pexels_help_3) echo "You can leave it empty and later add PEXELS_API_KEY to the .env file, then restart the containers." ;;
        fr:pexels_prompt) echo "Clé API Pexels (optionnelle, Entrée pour ignorer)" ;;
        us:pexels_prompt) echo "Pexels API key (optional, press Enter to skip)" ;;
        fr:pexels_configured) echo "Clé API Pexels configurée." ;;
        us:pexels_configured) echo "Pexels API key configured." ;;
        fr:pexels_skipped) echo "Clé API Pexels ignorée. La recherche d'images Pexels sera désactivée." ;;
        us:pexels_skipped) echo "Pexels API key skipped. Pexels image search will be disabled." ;;
        fr:data_dirs_header) echo "Dossiers de données" ;;
        us:data_dirs_header) echo "Data directories" ;;
        fr:media_dir_prompt) echo "Dossier des médias" ;;
        us:media_dir_prompt) echo "Media directory" ;;
        fr:private_dir_prompt) echo "Dossier des données privées" ;;
        us:private_dir_prompt) echo "Private data directory" ;;
        fr:dirs_created) echo "Dossiers créés." ;;
        us:dirs_created) echo "Directories created." ;;
        fr:env_header) echo "Génération du fichier .env" ;;
        us:env_header) echo "Generating .env file" ;;
        fr:env_backup) echo "Ancien .env sauvegardé dans .env.bak" ;;
        us:env_backup) echo "Previous .env saved to .env.bak" ;;
        fr:env_generated) echo "Fichier .env généré." ;;
        us:env_generated) echo ".env file generated." ;;
        fr:security_header) echo "Durcissement de sécurité" ;;
        us:security_header) echo "Security hardening" ;;
        fr:security_ok) echo "Sécurité vérifiée." ;;
        us:security_ok) echo "Security checks completed." ;;
        fr:security_failed) echo "Le durcissement de sécurité a échoué." ;;
        us:security_failed) echo "Security hardening failed." ;;
        fr:updating_header) echo "Mise à jour du dépôt" ;;
        us:updating_header) echo "Updating repository" ;;
        fr:update_branch) echo "Branche de mise à jour" ;;
        us:update_branch) echo "Update branch" ;;
        fr:repository_updated) echo "Dépôt mis à jour." ;;
        us:repository_updated) echo "Repository updated." ;;
        fr:starting_header) echo "Démarrage des conteneurs" ;;
        us:starting_header) echo "Starting containers" ;;
        fr:containers_started) echo "Conteneurs démarrés." ;;
        us:containers_started) echo "Containers started." ;;
        fr:complete) echo "Installation terminée !" ;;
        us:complete) echo "Installation complete!" ;;
        fr:update_complete) echo "Mise à jour terminée !" ;;
        us:update_complete) echo "Update complete!" ;;
        fr:admin_label) echo "Admin" ;;
        us:admin_label) echo "Admin" ;;
        fr:media_label) echo "Médias" ;;
        us:media_label) echo "Media" ;;
        fr:data_label) echo "Données" ;;
        us:data_label) echo "Data" ;;
        fr:keep_env_safe) echo "Conservez votre fichier .env en lieu sûr." ;;
        us:keep_env_safe) echo "Keep your .env file in a safe place." ;;
        *) echo "$key" ;;
    esac
}

generate_secret() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
    elif command -v python >/dev/null 2>&1; then
        python -c 'import secrets; print(secrets.token_urlsafe(48))'
    elif command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 48 | tr -d '\n'
        echo
    else
        die "$(msg secret_generation_failed)"
    fi
}

normalize_mode() {
    case "$(echo "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|install|installation|new|nouvelle) echo "install" ;;
        2|update|maj|mise-a-jour|mise_à_jour|miseajour) echo "update" ;;
        *) echo "" ;;
    esac
}

env_file_value() {
    local key="$1"
    local file="$2"
    local name value
    [ -f "$file" ] || return 0
    while IFS='=' read -r name value; do
        [ "$name" = "$key" ] || continue
        value="${value%\"}"
        value="${value#\"}"
        value="${value%\'}"
        value="${value#\'}"
        echo "$value"
        return 0
    done < "$file"
}

looks_like_visio_install() {
    local dir="$1"
    [ -d "$dir/.git" ] &&
    [ -f "$dir/docker-compose.yml" ] &&
    [ -f "$dir/scripts/security_bootstrap.sh" ] &&
    [ -f "$dir/web/app_bootstrap.py" ] &&
    [ -f "$dir/.env" ]
}

can_update_visio_install() {
    local dir="$1"
    [ -w "$dir" ] &&
    [ -w "$dir/.git" ] &&
    [ -w "$dir/.git/FETCH_HEAD" -o ! -e "$dir/.git/FETCH_HEAD" ]
}

run_security_bootstrap() {
    local mode="$1"
    local dir="$2"
    local security_log
    header "$(msg security_header)"
    security_log="$(mktemp)"
    if bash ./scripts/security_bootstrap.sh "$mode" "$dir" >"$security_log" 2>&1; then
        rm -f "$security_log"
        ok "$(msg security_ok)"
    else
        cat "$security_log" >&2
        rm -f "$security_log"
        die "$(msg security_failed)"
    fi
}

header "$(msg mode_header)"
INSTALL_MODE="$(normalize_mode "$REQUESTED_MODE")"
while [[ "$INSTALL_MODE" != "install" && "$INSTALL_MODE" != "update" ]]; do
    if [ -n "$REQUESTED_MODE" ]; then
        warn "$(msg invalid_mode)"
        REQUESTED_MODE=""
    fi
    read -rp "$(msg mode_prompt): " MODE_CHOICE
    INSTALL_MODE="$(normalize_mode "$MODE_CHOICE")"
    [ -n "$INSTALL_MODE" ] || warn "$(msg invalid_mode)"
done
if [ "$INSTALL_MODE" = "install" ]; then
    ok "$(msg mode_install)"
else
    ok "$(msg mode_update)"
fi

# ── Prerequisites ─────────────────────────────────────────────────────────────
header "$(msg checking_prerequisites)"

command -v docker  >/dev/null 2>&1 || die "$(msg docker_missing)"
docker compose version >/dev/null 2>&1 || die "$(msg compose_missing)"
command -v git     >/dev/null 2>&1 || die "$(msg git_missing)"

ok "$(msg prerequisites_ok)"

if [ "$INSTALL_MODE" = "update" ]; then
    # ── Existing installation directory ───────────────────────────────────────
    header "$(msg install_dir_header)"
    if looks_like_visio_install "$(pwd)"; then
        DEFAULT_UPDATE_DIR="$(pwd)"
    else
        DEFAULT_UPDATE_DIR="$DEFAULT_INSTALL_DIR"
    fi
    read -rp "$(msg update_dir_prompt) [${DEFAULT_UPDATE_DIR}]: " INSTALL_DIR
    INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_UPDATE_DIR}"

    [ -d "$INSTALL_DIR" ] || die "$(msg update_dir_missing) $INSTALL_DIR"
    looks_like_visio_install "$INSTALL_DIR" || die "$(msg update_dir_invalid) $INSTALL_DIR"
    can_update_visio_install "$INSTALL_DIR" || die "$(msg update_dir_not_writable) $INSTALL_DIR"

    cd "$INSTALL_DIR"
    UPDATE_BRANCH="$(env_file_value VISIO_UPDATE_BRANCH "$INSTALL_DIR/.env")"
    UPDATE_BRANCH="${UPDATE_BRANCH:-$DEFAULT_UPDATE_BRANCH}"

    # ── Repository update ────────────────────────────────────────────────────
    header "$(msg updating_header)"
    ok "$(msg update_branch): $UPDATE_BRANCH"
    git fetch origin "$UPDATE_BRANCH"
    git checkout "$UPDATE_BRANCH"
    git pull --ff-only origin "$UPDATE_BRANCH"
    ok "$(msg repository_updated)"

    run_security_bootstrap update "$INSTALL_DIR"

    # ── Launch ───────────────────────────────────────────────────────────────
    header "$(msg starting_header)"
    docker compose up -d --build
    ok "$(msg containers_started)"

    echo
    echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
    echo -e "${BOLD}  $(msg update_complete)${NC}"
    echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
    echo
    exit 0
fi

# ── Installation directory ────────────────────────────────────────────────────
header "$(msg install_dir_header)"
read -rp "$(msg install_dir_prompt) [${DEFAULT_INSTALL_DIR}]: " INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"

if [ -d "$INSTALL_DIR/.git" ]; then
    die "$(msg git_dir_exists) $INSTALL_DIR"
elif [ -d "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    die "$(msg dir_not_empty) $INSTALL_DIR"
else
    header "$(msg cloning_repository)"
    git clone --quiet --branch main "$REPO_URL" "$INSTALL_DIR"
    ok "$(msg repository_cloned) $INSTALL_DIR."
fi

cd "$INSTALL_DIR"

# ── Administrator account ─────────────────────────────────────────────────────
header "$(msg admin_header)"

while true; do
    read -rp "$(msg admin_user_prompt): " ADMIN_USER
    [[ -n "$ADMIN_USER" && "$ADMIN_USER" =~ ^[a-zA-Z0-9_.-]+$ ]] && break
    warn "$(msg invalid_admin_name)"
done

while true; do
    read -srp "$(msg admin_password_prompt): " ADMIN_PASSWORD; echo
    [[ ${#ADMIN_PASSWORD} -ge 10 ]] || { warn "$(msg password_too_short)"; continue; }
    read -srp "$(msg confirm_password_prompt): " ADMIN_PASSWORD2; echo
    [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD2" ]] && break
    warn "$(msg passwords_mismatch)"
done

ok "$(msg admin_configured): $ADMIN_USER"

# ── Port ──────────────────────────────────────────────────────────────────────
header "$(msg network_header)"
read -rp "$(msg port_prompt) [${DEFAULT_PORT}]: " PORT
PORT="${PORT:-$DEFAULT_PORT}"

# ── Clean existing data ───────────────────────────────────────────────────────
header "$(msg cleanup_header)"

warn "$(msg cleanup_warning)"
read -rp "$(msg continue_prompt)"

PROJECT_NAME="$(basename "$INSTALL_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
docker compose down --remove-orphans 2>/dev/null || true
for vol in postgres_data redis_data; do
    VNAME="${PROJECT_NAME}_${vol}"
    if docker volume inspect "$VNAME" >/dev/null 2>&1; then
        docker volume rm "$VNAME" >/dev/null
        ok "$(msg volume_removed): $VNAME."
    fi
done

# ── PostgreSQL password ───────────────────────────────────────────────────────
header "$(msg postgres_header)"

while true; do
    read -srp "$(msg postgres_password_prompt): " POSTGRES_PASSWORD; echo
    [[ ${#POSTGRES_PASSWORD} -ge 10 ]] || { warn "$(msg password_too_short)"; continue; }
    read -srp "$(msg confirm_password_prompt): " POSTGRES_PASSWORD2; echo
    [[ "$POSTGRES_PASSWORD" == "$POSTGRES_PASSWORD2" ]] && break
    warn "$(msg passwords_mismatch)"
done

ok "$(msg postgres_configured)"

# ── Application secrets ───────────────────────────────────────────────────────
SECRET_KEY="$(generate_secret)"
CLIENT_HEARTBEAT_TOKEN="$(generate_secret)"
DISPLAY_API_TOKEN="$(generate_secret)"
UPDATER_API_TOKEN="$(generate_secret)"

# ── Optional external image provider ─────────────────────────────────────────
header "$(msg pexels_header)"
echo "$(msg pexels_help_1)"
echo "$(msg pexels_help_2)"
echo "$(msg pexels_help_3)"
echo
read -srp "$(msg pexels_prompt): " PEXELS_API_KEY; echo
if [ -n "$PEXELS_API_KEY" ]; then
    PEXELS_API_KEY_VALUE="$PEXELS_API_KEY"
    ok "$(msg pexels_configured)"
else
    PEXELS_API_KEY_VALUE=""
    warn "$(msg pexels_skipped)"
fi

# ── Data directories ──────────────────────────────────────────────────────────
header "$(msg data_dirs_header)"

MEDIA_DIR_DEFAULT="$INSTALL_DIR/media"
PRIVATE_DIR_DEFAULT="$INSTALL_DIR/private"

read -rp "$(msg media_dir_prompt) [${MEDIA_DIR_DEFAULT}]: " MEDIA_DIR
MEDIA_DIR="${MEDIA_DIR:-$MEDIA_DIR_DEFAULT}"

read -rp "$(msg private_dir_prompt) [${PRIVATE_DIR_DEFAULT}]: " PRIVATE_DIR
PRIVATE_DIR="${PRIVATE_DIR:-$PRIVATE_DIR_DEFAULT}"

mkdir -p "$MEDIA_DIR" "$PRIVATE_DIR"
ok "$(msg dirs_created)"

# ── .env file ─────────────────────────────────────────────────────────────────
header "$(msg env_header)"

if [ -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak"
    warn "$(msg env_backup)"
fi

cat > "$INSTALL_DIR/.env" <<EOF
ADMIN_USER=${ADMIN_USER}
ADMIN_PASSWORD=${ADMIN_PASSWORD}
SECRET_KEY=${SECRET_KEY}
PORT=${PORT}
VISIO_HOST_ROOT=${INSTALL_DIR}
MEDIA_DIR=${MEDIA_DIR}
PRIVATE_DIR=${PRIVATE_DIR}
POSTGRES_USER=visio
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=visio
CLIENT_HEARTBEAT_TOKEN=${CLIENT_HEARTBEAT_TOKEN}
DISPLAY_API_TOKEN=${DISPLAY_API_TOKEN}
UPDATER_API_TOKEN=${UPDATER_API_TOKEN}
PEXELS_API_KEY=${PEXELS_API_KEY_VALUE}
VISIO_UPDATE_BRANCH=${DEFAULT_UPDATE_BRANCH}
COMPOSE_PROJECT_NAME=${PROJECT_NAME}
EOF

chmod 600 "$INSTALL_DIR/.env"
ok "$(msg env_generated)"

run_security_bootstrap install "$INSTALL_DIR"

# ── Launch ────────────────────────────────────────────────────────────────────
header "$(msg starting_header)"

cd "$INSTALL_DIR"
docker compose pull --quiet 2>/dev/null || true
docker compose up -d --build

ok "$(msg containers_started)"

# ── Summary ───────────────────────────────────────────────────────────────────
echo
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo -e "${BOLD}  $(msg complete)${NC}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${NC}"
echo
echo -e "  URL        : ${CYAN}http://$(hostname -I | awk '{print $1}'):${PORT}${NC}"
echo -e "  $(msg admin_label)      : ${BOLD}${ADMIN_USER}${NC}"
echo -e "  $(msg media_label)      : ${MEDIA_DIR}"
echo -e "  $(msg data_label)       : ${PRIVATE_DIR}"
echo
echo -e "  ${YELLOW}$(msg keep_env_safe)${NC}"
echo
