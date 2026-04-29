#!/usr/bin/env bash
set -euo pipefail

TARGET_VERSION="${1:-}"

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
    echo "Tag $TARGET_VERSION introuvable, pull origin main"
    git pull --ff-only origin main
  fi
else
  echo "Pull origin main"
  git pull --ff-only origin main
fi

echo "Version installée: $(cat VERSION 2>/dev/null || true)"
echo "Mise à jour terminée"
