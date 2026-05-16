#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "Mise a jour de Visio depuis la branche main..."
git fetch origin main
git checkout main
git pull --ff-only origin main

if [ "${VISIO_SKIP_DOCKER_RESTART:-}" = "1" ]; then
  echo "Redemarrage Docker ignore par l'administration."
  echo "Termine."
  exit 0
fi

echo "Redemarrage de Visio..."
if docker compose version >/dev/null 2>&1; then
  docker compose up -d --build
else
  docker-compose up -d --build
fi

echo "Termine."
