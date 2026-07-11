# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint

# Ré-exporté volontairement : appelé dynamiquement via sys.modules['blueprints.settings']
# (voir blueprints/settings/backups.py) et patché par les tests.
from services.backup_svc import copy_backup_to_smb  # noqa: F401

bp = Blueprint('settings', __name__)

from . import accounts, backups, features, installation, language, main, screens, theme  # noqa: E402,F401
