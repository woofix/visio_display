#!/usr/bin/env bash
set -euo pipefail

SUPPORTED_POSTGRES_IMAGE="postgres:16.13-alpine"
SUPPORTED_POSTGRES_MAJOR="16"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD=(docker-compose)
else
  echo "docker compose ou docker-compose est requis." >&2
  exit 1
fi

timestamp="$(date +"%Y%m%d-%H%M%S")"
default_target="$ROOT_DIR/backups/visio-backup-$timestamp"
target_dir="${1:-$default_target}"

mkdir -p "$target_dir"

set -a
if [ -f "$ROOT_DIR/.env" ]; then
  . "$ROOT_DIR/.env"
fi
set +a

media_dir="${MEDIA_DIR:?MEDIA_DIR absent. Lancez le module d'installation ou renseignez .env.}"
private_dir="${PRIVATE_DIR:?PRIVATE_DIR absent. Lancez le module d'installation ou renseignez .env.}"
postgres_db="${POSTGRES_DB:-visio}"
postgres_user="${POSTGRES_USER:-visio}"

resolve_path() {
  local value="$1"
  if [ -z "$value" ]; then
    return 1
  fi
  if [ "${value#/}" != "$value" ]; then
    printf '%s\n' "$value"
  else
    printf '%s\n' "$ROOT_DIR/$value"
  fi
}

media_dir="$(resolve_path "$media_dir")"
private_dir="$(resolve_path "$private_dir")"
backup_dir_basename="$(basename "$private_dir")/backups"

echo "Preparation des services PostgreSQL/Redis..."
"${COMPOSE_CMD[@]}" pull postgres >/dev/null
"${COMPOSE_CMD[@]}" up -d postgres redis >/dev/null

echo "Attente de PostgreSQL..."
until "${COMPOSE_CMD[@]}" exec -T postgres pg_isready -U "$postgres_user" -d "$postgres_db" >/dev/null 2>&1; do
  sleep 1
done

server_version="$("${COMPOSE_CMD[@]}" exec -T postgres psql -U "$postgres_user" -d "$postgres_db" -Atqc "SHOW server_version")"
server_major="${server_version%%.*}"
if [ "$server_major" != "$SUPPORTED_POSTGRES_MAJOR" ]; then
  echo "Version PostgreSQL incompatible: $server_version. Version attendue: majeure $SUPPORTED_POSTGRES_MAJOR via $SUPPORTED_POSTGRES_IMAGE." >&2
  exit 1
fi

echo "Export PostgreSQL..."
"${COMPOSE_CMD[@]}" exec -T postgres pg_dump -U "$postgres_user" -d "$postgres_db" -Fc > "$target_dir/postgres.dump"

echo "Archivage des medias..."
mkdir -p "$media_dir"
tar -C "$media_dir" -czf "$target_dir/media.tar.gz" .

echo "Archivage des fichiers prives..."
mkdir -p "$private_dir"
if [ -d "$private_dir/backups" ]; then
  tar -C "$private_dir" --exclude "./backups" -czf "$target_dir/private.tar.gz" .
else
  tar -C "$private_dir" -czf "$target_dir/private.tar.gz" .
fi

if [ -f "$ROOT_DIR/.env" ]; then
  cp "$ROOT_DIR/.env" "$target_dir/env.backup"
fi

cat > "$target_dir/manifest.json" <<JSON
{
  "version": 3,
  "created_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "database_dump": "postgres.dump",
  "media_archive": "media.tar.gz",
  "private_archive": "private.tar.gz",
  "env_file": $( [ -f "$target_dir/env.backup" ] && printf '"env.backup"' || printf 'null' ),
  "postgres_server_version": "$server_version",
  "postgres_server_major": $server_major,
  "postgres_supported_major": $SUPPORTED_POSTGRES_MAJOR,
  "postgres_supported_image": "$SUPPORTED_POSTGRES_IMAGE"
}
JSON

echo "Sauvegarde creee dans: $target_dir"
