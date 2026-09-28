#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
HOST_ROOT="${VISIO_HOST_ROOT:-$ROOT_DIR}"
MARKER="$ROOT_DIR/data/.storage-v1"
POSTGRES_DEST="$ROOT_DIR/data/postgres"
REDIS_DEST="$ROOT_DIR/data/redis"

volume_for() {
  service="$1"
  found="$(docker volume ls \
    --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter "label=com.docker.compose.volume=$service" \
    --format '{{.Name}}' | head -n 1)"
  if [ -n "$found" ]; then
    printf '%s\n' "$found"
  elif docker volume inspect "${PROJECT_NAME}_${service}" >/dev/null 2>&1; then
    printf '%s\n' "${PROJECT_NAME}_${service}"
  fi
}

container_for() {
  service="$1"
  docker ps --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter "label=com.docker.compose.service=$service" \
    --format '{{.ID}}' | head -n 1
}

if [ -f "$MARKER" ]; then
  echo "Stockage Visio deja regroupe dans $HOST_ROOT/data."
  exit 0
fi

mkdir -p "$ROOT_DIR/data"
postgres_volume="$(volume_for postgres_data)"
redis_volume="$(volume_for redis_data)"

if [ -z "$postgres_volume" ] && [ -z "$redis_volume" ]; then
  mkdir -p "$POSTGRES_DEST" "$REDIS_DEST"
  printf 'created_at=%s\nsource=new-installation\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$MARKER"
  echo "Stockage Visio initialise dans $HOST_ROOT/data."
  exit 0
fi

if [ -z "$postgres_volume" ] || [ -z "$redis_volume" ]; then
  echo "Migration refusee: un seul des deux anciens volumes Docker a ete trouve." >&2
  exit 1
fi

if [ -e "$POSTGRES_DEST" ] && [ -n "$(find "$POSTGRES_DEST" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "Migration refusee: $POSTGRES_DEST contient deja des donnees." >&2
  exit 1
fi
if [ -e "$REDIS_DEST" ] && [ -n "$(find "$REDIS_DEST" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "Migration refusee: $REDIS_DEST contient deja des donnees." >&2
  exit 1
fi

postgres_container="$(container_for postgres)"
redis_container="$(container_for redis)"
if [ -z "$postgres_container" ] || [ -z "$redis_container" ]; then
  echo "Migration refusee: PostgreSQL et Redis doivent fonctionner avant la mise a jour." >&2
  exit 1
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
backup_local="$ROOT_DIR/private/backups/storage-migration-$timestamp"
backup_host="$HOST_ROOT/private/backups/storage-migration-$timestamp"
mkdir -p "$backup_local"

echo "Sauvegarde PostgreSQL avant migration..."
docker exec "$postgres_container" pg_dump \
  -U "${POSTGRES_USER:-visio}" -d "${POSTGRES_DB:-visio}" -Fc \
  > "$backup_local/postgres.dump"
test -s "$backup_local/postgres.dump"

echo "Sauvegarde Redis avant migration..."
docker exec "$redis_container" redis-cli SAVE >/dev/null
docker run --rm \
  -v "$redis_volume:/source:ro" \
  -v "$backup_host:/backup" \
  redis:7-alpine sh -c 'tar -C /source -czf /backup/redis-data.tar.gz .'

running_ids="$(docker ps --filter "label=com.docker.compose.project=$PROJECT_NAME" --format '{{.ID}}')"
rollback_needed=1
rollback() {
  code=$?
  if [ "$rollback_needed" -eq 1 ] && [ -n "$running_ids" ]; then
    echo "Echec de migration: redemarrage des anciens conteneurs." >&2
    # shellcheck disable=SC2086
    docker start $running_ids >/dev/null 2>&1 || true
  fi
  exit "$code"
}
trap rollback EXIT INT TERM

echo "Arret temporaire de Visio..."
# shellcheck disable=SC2086
docker stop $running_ids >/dev/null

rm -rf "$ROOT_DIR/data/.postgres.migrating" "$ROOT_DIR/data/.redis.migrating"
mkdir -p "$ROOT_DIR/data/.postgres.migrating" "$ROOT_DIR/data/.redis.migrating"

echo "Copie de PostgreSQL dans le repertoire Visio..."
docker run --rm \
  -v "$postgres_volume:/source:ro" \
  -v "$HOST_ROOT/data/.postgres.migrating:/target" \
  postgres:16.13-alpine sh -c 'cp -a /source/. /target/'

echo "Copie de Redis dans le repertoire Visio..."
docker run --rm \
  -v "$redis_volume:/source:ro" \
  -v "$HOST_ROOT/data/.redis.migrating:/target" \
  redis:7-alpine sh -c 'cp -a /source/. /target/'

test -n "$(find "$ROOT_DIR/data/.postgres.migrating" -mindepth 1 -maxdepth 1 -print -quit)"
test -n "$(find "$ROOT_DIR/data/.redis.migrating" -mindepth 1 -maxdepth 1 -print -quit)"
rm -rf "$POSTGRES_DEST" "$REDIS_DEST"
mv "$ROOT_DIR/data/.postgres.migrating" "$POSTGRES_DEST"
mv "$ROOT_DIR/data/.redis.migrating" "$REDIS_DEST"

cat > "$MARKER" <<EOF
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
postgres_source=$postgres_volume
redis_source=$redis_volume
backup=$backup_host
EOF

# Keep the first upgrade from an older updater safe: that updater restarted
# only app/worker with --no-deps after running this newly downloaded script.
# Start the migrated databases here before handing control back to it.
echo "Redemarrage de PostgreSQL et Redis sur le nouveau stockage..."
if docker compose version >/dev/null 2>&1; then
  docker compose --project-name "$PROJECT_NAME" up -d postgres redis
else
  docker-compose --project-name "$PROJECT_NAME" up -d postgres redis
fi

rollback_needed=0
trap - EXIT INT TERM
echo "Migration terminee. Les anciens volumes Docker sont conserves pour le retour arriere."
