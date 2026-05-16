#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "Mise a jour de Visio depuis la branche main..."
git fetch origin main
git checkout main
git pull --ff-only origin main

echo "Redemarrage de Visio..."
if docker compose version >/dev/null 2>&1; then
  docker compose up -d --build
else
  docker-compose up -d --build
fi

echo "Termine."
