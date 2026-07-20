#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

LOG_DIR="${PRIVATE_DIR:-.}/update_logs"
if ! mkdir -p "$LOG_DIR" 2>/dev/null; then
  LOG_DIR="./update_logs"
  mkdir -p "$LOG_DIR"
fi
LOG_FILE="$LOG_DIR/update-dev-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1
trap 'ec=$?; status=success; [ "$ec" -ne 0 ] && status=error; echo "STATUS=$status EXIT_CODE=$ec" >> "$LOG_FILE"' EXIT

echo "Mise a jour de Visio depuis la branche dev..."
git fetch origin dev
git checkout dev
git pull --ff-only origin dev

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
