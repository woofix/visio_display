#!/bin/sh
# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
HOOKS_DIR="$ROOT_DIR/.githooks"
PRE_COMMIT="$HOOKS_DIR/pre-commit"

if ! command -v git >/dev/null 2>&1; then
    echo "erreur: git n'est pas installé sur cette machine." >&2
    exit 1
fi

if ! git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "erreur: $ROOT_DIR n'est pas un dépôt Git." >&2
    echo "Lancez ce script sur le serveur ramses, dans le dossier cloné du projet." >&2
    exit 1
fi

if [ ! -f "$PRE_COMMIT" ]; then
    echo "erreur: hook introuvable: $PRE_COMMIT" >&2
    exit 1
fi

chmod +x "$PRE_COMMIT"
git -C "$ROOT_DIR" config core.hooksPath .githooks

echo "OK: hooks Git activés pour Visio-Display."
echo "À chaque commit, VERSION sera incrémenté automatiquement selon les fichiers modifiés."
echo "Options ponctuelles:"
echo "  VISIO_VERSION_BUMP=auto  git commit ..."
echo "  VISIO_VERSION_BUMP=minor git commit ..."
echo "  VISIO_VERSION_BUMP=major git commit ..."
echo "  VISIO_VERSION_BUMP=none  git commit ..."
