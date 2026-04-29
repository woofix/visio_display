#!/bin/sh

# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENV_FILE="${VISIO_ENV_FILE:-/app/.env}"
SECURITY_BOOTSTRAP="${VISIO_SECURITY_BOOTSTRAP:-$APP_DIR/scripts/security_bootstrap.sh}"

if [ -x "$SECURITY_BOOTSTRAP" ]; then
    VISIO_ENV_FILE="$ENV_FILE" "$SECURITY_BOOTSTRAP" check "$APP_DIR" || \
        echo "warning: contrôle sécurité non bloquant en échec" >&2
else
    echo "warning: script de contrôle sécurité introuvable: $SECURITY_BOOTSTRAP" >&2
fi

exec "$@"
