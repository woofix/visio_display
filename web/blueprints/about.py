# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import subprocess

from flask import Blueprint, render_template, session

from blueprints.guards import admin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path

bp = Blueprint('about', __name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_version():
    v = os.environ.get('APP_VERSION', '').strip()
    if v:
        return v
    version_file = os.path.join(_BASE_DIR, '..', 'VERSION')
    try:
        with open(os.path.normpath(version_file)) as f:
            return f.read().strip() or '1.0.0'
    except OSError:
        pass
    return '1.0.0'


def _get_git_commit():
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=2,
            cwd=_BASE_DIR,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return os.environ.get('GIT_COMMIT', '').strip() or None


def _license_exists():
    return os.path.isfile(os.path.normpath(os.path.join(_BASE_DIR, '..', 'LICENSE')))


@bp.route('/admin/about')
def about_page():
    redir = admin_guard()
    if redir:
        return redir
    cfg = load_config()
    return render_template(
        'admin_about.html',
        cfg=cfg,
        current_user=session.get('user'),
        logo_path=get_logo_path(),
        app_version=_get_version(),
        git_commit=_get_git_commit(),
        license_exists=_license_exists(),
    )
