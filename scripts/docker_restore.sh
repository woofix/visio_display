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

force_env=0
if [ "${1:-}" = "--force-env" ]; then
  force_env=1
  shift
fi

backup_dir="${1:-}"
if [ -z "$backup_dir" ]; then
  echo "Usage: scripts/docker_restore.sh [--force-env] <dossier-sauvegarde>" >&2
  exit 1
fi

if [ ! -d "$backup_dir" ]; then
  echo "Dossier de sauvegarde introuvable: $backup_dir" >&2
  exit 1
fi

if [ ! -f "$backup_dir/postgres.dump" ] || [ ! -f "$backup_dir/media.tar.gz" ] || [ ! -f "$backup_dir/private.tar.gz" ]; then
  echo "Sauvegarde incomplete: postgres.dump, media.tar.gz et private.tar.gz sont requis." >&2
  exit 1
fi

if [ ! -f "$backup_dir/manifest.json" ]; then
  echo "Sauvegarde invalide: manifest.json est requis." >&2
  exit 1
fi

manifest_version="$(python3 - <<'PY' "$backup_dir/manifest.json"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    data = json.load(handle)
print(data.get('version', ''))
PY
)"
manifest_major="$(python3 - <<'PY' "$backup_dir/manifest.json"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    data = json.load(handle)
print(data.get('postgres_supported_major', ''))
PY
)"

if [ "$manifest_version" != "3" ]; then
  echo "Format de sauvegarde incompatible: version $manifest_version, attendue 3." >&2
  exit 1
fi

if [ "$manifest_major" != "$SUPPORTED_POSTGRES_MAJOR" ]; then
  echo "Sauvegarde incompatible avec cette pile PostgreSQL: archive=$manifest_major, attendu=$SUPPORTED_POSTGRES_MAJOR." >&2
  exit 1
fi

if [ -f "$backup_dir/env.backup" ] && { [ ! -f "$ROOT_DIR/.env" ] || [ "$force_env" -eq 1 ]; }; then
  cp "$backup_dir/env.backup" "$ROOT_DIR/.env"
fi

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
mkdir -p "$media_dir" "$private_dir"

echo "Arret temporaire de l'application..."
"${COMPOSE_CMD[@]}" stop app worker >/dev/null 2>&1 || true

echo "Demarrage de PostgreSQL/Redis..."
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

echo "Restauration des medias..."
find "$media_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
tar -C "$media_dir" -xzf "$backup_dir/media.tar.gz"

echo "Restauration des fichiers prives..."
mkdir -p "$private_dir/backups"
find "$private_dir" -mindepth 1 -maxdepth 1 ! -name backups -exec rm -rf {} +
tar -C "$private_dir" -xzf "$backup_dir/private.tar.gz"

echo "Restauration PostgreSQL..."
cat "$backup_dir/postgres.dump" | "${COMPOSE_CMD[@]}" exec -T postgres pg_restore \
  -U "$postgres_user" \
  -d "$postgres_db" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges

echo "Redemarrage de la stack..."
"${COMPOSE_CMD[@]}" up -d >/dev/null

echo "Restauration terminee."
