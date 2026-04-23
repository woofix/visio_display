#!/bin/sh

# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENV_FILE="${VISIO_ENV_FILE:-/app/.env}"
DATA_DIR="${VISIO_DATA_DIR:-$APP_DIR/data/private}"
DB_FILE="${VISIO_DB_FILE:-${DATA_DIR%/}/visio-display.db}"
PLACEHOLDER_SECRET="remplace_par_une_chaine_aleatoire"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "Aucun interpreteur Python disponible pour generer SECRET_KEY." >&2
    exit 1
fi

is_usable_secret() {
    value="${1:-}"
    [ -n "$value" ] && [ "$value" != "$PLACEHOLDER_SECRET" ]
}

persist_secret_key() {
    secret="$1"
    tmp_file="$(mktemp)"

    awk -v secret="$secret" '
        BEGIN { updated = 0 }
        /^SECRET_KEY=/ && updated == 0 {
            print "SECRET_KEY=" secret
            updated = 1
            next
        }
        { print }
        END {
            if (updated == 0) {
                print "SECRET_KEY=" secret
            }
        }
    ' "$ENV_FILE" > "$tmp_file"

    cat "$tmp_file" > "$ENV_FILE"
    rm -f "$tmp_file"
}

if [ ! -f "$DB_FILE" ]; then
    if ! is_usable_secret "${SECRET_KEY:-}"; then
        generated_secret="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_hex(32))')"
        export SECRET_KEY="$generated_secret"

        if [ -f "$ENV_FILE" ] && [ -w "$ENV_FILE" ]; then
            persist_secret_key "$generated_secret"
            echo "SECRET_KEY generee et enregistree dans $ENV_FILE (premier demarrage)."
        else
            echo "SECRET_KEY generee pour ce premier demarrage, mais $ENV_FILE est introuvable ou non inscriptible." >&2
        fi
    fi
fi

exec "$@"
