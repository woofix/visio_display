#!/bin/sh

# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ENV_FILE="${VISIO_ENV_FILE:-/app/.env}"
SECURITY_BOOTSTRAP="${VISIO_SECURITY_BOOTSTRAP:-$APP_DIR/scripts/security_bootstrap.sh}"
VISIO_GIT_ROOT="${VISIO_GIT_ROOT:-/opt/visio-display}"

if command -v git >/dev/null 2>&1 && [ -d "$VISIO_GIT_ROOT/.git" ]; then
    git config --global --add safe.directory "$VISIO_GIT_ROOT" || \
        echo "warning: unable to mark Git repository as safe: $VISIO_GIT_ROOT" >&2
fi

if [ -x "$SECURITY_BOOTSTRAP" ]; then
    VISIO_ENV_FILE="$ENV_FILE" "$SECURITY_BOOTSTRAP" check "$APP_DIR" || \
        echo "warning: non-blocking security check failed" >&2
else
    echo "warning: security check script not found: $SECURITY_BOOTSTRAP" >&2
fi

exec "$@"
