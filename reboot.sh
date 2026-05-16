#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

REMOTE="${VISIO_UPDATE_REMOTE:-origin}"
BRANCH="${VISIO_UPDATE_BRANCH:-main}"
TARGET_VERSION="${1:-}"

usage() {
  cat <<'EOF'
Usage: ./reboot.sh [version-ou-tag]

Met a jour Visio depuis Git, reconstruit les images Docker, puis redemarre
la stack Docker Compose.

Variables optionnelles:
  VISIO_UPDATE_REMOTE   Remote Git a utiliser (defaut: origin)
  VISIO_UPDATE_BRANCH   Branche Git a utiliser (defaut: main)

Exemples:
  ./reboot.sh
  ./reboot.sh 1.8.5
  VISIO_UPDATE_BRANCH=dev ./reboot.sh
EOF
}

log() {
  printf '\n==> %s\n' "$1"
}

fail() {
  printf 'Erreur: %s\n' "$1" >&2
  exit 1
}

validate_git_name() {
  local label="$1"
  local value="$2"

  case "$value" in
    ""| -*|*..*|*[[:space:]~^:?*\\[]*)
      fail "$label invalide: $value"
      ;;
  esac
}

compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    printf 'docker compose'
  elif command -v docker-compose >/dev/null 2>&1; then
    printf 'docker-compose'
  else
    fail "Docker Compose est introuvable"
  fi
}

checkout_update_branch() {
  if ! git rev-parse --verify --quiet "refs/remotes/$REMOTE/$BRANCH" >/dev/null; then
    fail "branche distante introuvable: $REMOTE/$BRANCH"
  fi

  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"

  if [ "$current_branch" = "$BRANCH" ]; then
    return
  fi

  if git rev-parse --verify --quiet "refs/heads/$BRANCH" >/dev/null; then
    git checkout "$BRANCH"
  else
    git checkout -b "$BRANCH" --track "$REMOTE/$BRANCH"
  fi
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

validate_git_name "remote Git" "$REMOTE"
validate_git_name "branche Git" "$BRANCH"

log "Verification du dossier Visio"
[ -f "docker-compose.yml" ] || fail "docker-compose.yml introuvable dans $SCRIPT_DIR"
[ -d ".git" ] || fail "depot Git introuvable dans $SCRIPT_DIR"

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
  fail "remote Git introuvable: $REMOTE"
fi

DIRTY_STATUS="$(git status --porcelain | grep -v '^\?\? reboot\.sh$' || true)"
if [ -n "$DIRTY_STATUS" ]; then
  printf '%s\n' "$DIRTY_STATUS"
  fail "le depot Git n'est pas propre. Commit, stash ou supprime les changements avant la mise a jour"
fi

COMPOSE="$(compose_cmd)"

log "Recuperation des mises a jour Git"
git fetch "$REMOTE" --tags --prune

if [ -n "$TARGET_VERSION" ]; then
  log "Mise a jour vers $TARGET_VERSION"
  if git rev-parse --verify --quiet "refs/tags/$TARGET_VERSION" >/dev/null; then
    git checkout "$TARGET_VERSION"
  elif git rev-parse --verify --quiet "refs/tags/v$TARGET_VERSION" >/dev/null; then
    git checkout "v$TARGET_VERSION"
  else
    checkout_update_branch
    git pull --ff-only "$REMOTE" "$BRANCH"
  fi
else
  log "Mise a jour vers $REMOTE/$BRANCH"
  checkout_update_branch
  git pull --ff-only "$REMOTE" "$BRANCH"
fi

log "Preparation de la configuration locale"
scripts/security_bootstrap.sh update . || fail "configuration locale incomplete"

log "Reconstruction et redemarrage de Visio"
$COMPOSE up -d --build --remove-orphans

log "Etat des conteneurs"
$COMPOSE ps

log "Termine"
printf 'Visio est mis a jour et redemarre.\n'
