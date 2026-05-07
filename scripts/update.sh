#!/usr/bin/env bash
set -euo pipefail

TARGET_VERSION="${1:-}"
APP_DIR="${VISIO_APP_DIR:-/app}"
UPDATE_BRANCH="${VISIO_UPDATE_BRANCH:-main}"
UPDATE_REMOTE="${VISIO_UPDATE_REMOTE:-origin}"

case "$UPDATE_BRANCH" in
  ""| -*|*..*|*[[:space:]~^:?*\\[]*)
    echo "Erreur: branche de mise à jour invalide: $UPDATE_BRANCH"
    exit 1
    ;;
esac
case "$UPDATE_REMOTE" in
  ""| -*|*..*|*[[:space:]~^:?*\\[]*)
    echo "Erreur: remote de mise à jour invalide: $UPDATE_REMOTE"
    exit 1
    ;;
esac

echo "Répertoire: $(pwd)"
echo "Vérification du dépôt Git"

if [ ! -d ".git" ]; then
  echo "Erreur: dépôt Git introuvable"
  exit 1
fi

if ! git remote get-url "$UPDATE_REMOTE" >/dev/null 2>&1; then
  echo "Erreur: remote Git introuvable: $UPDATE_REMOTE"
  exit 1
fi

if ! git rev-parse --verify --quiet HEAD >/dev/null; then
  echo "Erreur: commit courant illisible"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Erreur: dépôt Git non propre"
  git status --short
  exit 1
fi

if ! command -v docker >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
  echo "Erreur: Docker Compose est requis pour finaliser la mise à jour"
  exit 1
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "Docker Compose disponible: docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  echo "Docker Compose disponible: docker-compose"
else
  echo "Erreur: Docker Compose est introuvable ou inaccessible"
  exit 1
fi

echo "Récupération des tags et branches"
git fetch "$UPDATE_REMOTE" --tags --prune

checkout_update_branch() {
  if ! git rev-parse --verify --quiet "refs/remotes/$UPDATE_REMOTE/$UPDATE_BRANCH" >/dev/null; then
    echo "Erreur: branche distante introuvable: $UPDATE_REMOTE/$UPDATE_BRANCH"
    exit 1
  fi

  CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$CURRENT_BRANCH" = "$UPDATE_BRANCH" ]; then
    return
  fi

  if git rev-parse --verify --quiet "refs/heads/$UPDATE_BRANCH" >/dev/null; then
    echo "Checkout de la branche cible $UPDATE_BRANCH"
    git checkout "$UPDATE_BRANCH"
  else
    echo "Création de la branche locale $UPDATE_BRANCH depuis $UPDATE_REMOTE/$UPDATE_BRANCH"
    git checkout -b "$UPDATE_BRANCH" --track "$UPDATE_REMOTE/$UPDATE_BRANCH"
  fi
}

if [ -n "$TARGET_VERSION" ]; then
  if git rev-parse --verify --quiet "refs/tags/$TARGET_VERSION" >/dev/null; then
    echo "Checkout du tag $TARGET_VERSION"
    git checkout "$TARGET_VERSION"
  elif git rev-parse --verify --quiet "refs/tags/v$TARGET_VERSION" >/dev/null; then
    echo "Checkout du tag v$TARGET_VERSION"
    git checkout "v$TARGET_VERSION"
  else
    checkout_update_branch
    echo "Tag $TARGET_VERSION introuvable, pull $UPDATE_REMOTE $UPDATE_BRANCH"
    git pull --ff-only "$UPDATE_REMOTE" "$UPDATE_BRANCH"
  fi
else
  checkout_update_branch
  echo "Pull $UPDATE_REMOTE $UPDATE_BRANCH"
  git pull --ff-only "$UPDATE_REMOTE" "$UPDATE_BRANCH"
fi

if [ -d "$APP_DIR" ] && [ -d "web" ] && [ "$(CDPATH= cd -- "$APP_DIR" && pwd)" != "$(pwd)" ]; then
  echo "Synchronisation du code applicatif vers $APP_DIR"
  cp -a web/. "$APP_DIR"/
  cp -f VERSION /VERSION 2>/dev/null || true
  if [ -d scripts ]; then
    mkdir -p "$APP_DIR/scripts"
    cp -a scripts/. "$APP_DIR/scripts"/
    chmod +x "$APP_DIR"/scripts/*.sh 2>/dev/null || true
  fi
  if [ -f "$APP_DIR/requirements.txt" ]; then
    echo "Vérification des dépendances Python"
    python -m pip install --no-cache-dir -r "$APP_DIR/requirements.txt"
  fi
fi

echo "Version installée: $(cat VERSION 2>/dev/null || true)"
echo "Mise à jour terminée"
