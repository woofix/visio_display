#!/usr/bin/env bash
set -euo pipefail

TARGET_VERSION="${1:-}"
APP_DIR="${VISIO_APP_DIR:-/app}"
UPDATE_BRANCH="${VISIO_UPDATE_BRANCH:-main}"

case "$UPDATE_BRANCH" in
  ""| -*|*..*|*[[:space:]~^:?*\\[]*)
    echo "Erreur: branche de mise à jour invalide: $UPDATE_BRANCH"
    exit 1
    ;;
esac

echo "Répertoire: $(pwd)"
echo "Vérification du dépôt Git"

if [ ! -d ".git" ]; then
  echo "Erreur: dépôt Git introuvable"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "Erreur: dépôt Git non propre"
  git status --short
  exit 1
fi

echo "Récupération des tags et branches"
git fetch --tags --prune

if [ -n "$TARGET_VERSION" ]; then
  if git rev-parse --verify --quiet "refs/tags/$TARGET_VERSION" >/dev/null; then
    echo "Checkout du tag $TARGET_VERSION"
    git checkout "$TARGET_VERSION"
  elif git rev-parse --verify --quiet "refs/tags/v$TARGET_VERSION" >/dev/null; then
    echo "Checkout du tag v$TARGET_VERSION"
    git checkout "v$TARGET_VERSION"
  else
    echo "Tag $TARGET_VERSION introuvable, pull origin $UPDATE_BRANCH"
    git pull --ff-only origin "$UPDATE_BRANCH"
  fi
else
  echo "Pull origin $UPDATE_BRANCH"
  git pull --ff-only origin "$UPDATE_BRANCH"
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
