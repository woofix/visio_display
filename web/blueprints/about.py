# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import subprocess

from flask import Blueprint, render_template, session

from blueprints.guards import admin_guard
from services.config_svc import load_config
from services.media_svc import get_logo_path

bp = Blueprint('about', __name__)

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RELEASES_URL = 'https://github.com/woofix/visio_display/releases/tag'


def _get_version():
    v = os.environ.get('APP_VERSION', '').strip()
    if v:
        return v
    version_files = []
    git_root = os.environ.get('VISIO_GIT_ROOT', '').strip()
    if git_root:
        version_files.append(os.path.join(git_root, 'VERSION'))
    version_files.append(os.path.join(_BASE_DIR, '..', 'VERSION'))
    version_files.append('/VERSION')

    seen = set()
    for version_file in version_files:
        version_file = os.path.normpath(version_file)
        if version_file in seen:
            continue
        seen.add(version_file)
        try:
            with open(version_file, encoding='utf-8') as f:
                version = f.read().strip()
            if version:
                return version
        except OSError:
            continue
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


def _get_release_url(version):
    clean_version = str(version or '').strip()
    if not clean_version:
        return None
    releases_url = os.environ.get('APP_RELEASES_URL', DEFAULT_RELEASES_URL).strip().rstrip('/')
    return f'{releases_url}/{clean_version}'


def _license_exists():
    return os.path.isfile(os.path.normpath(os.path.join(_BASE_DIR, '..', 'LICENSE')))


@bp.route('/admin/about')
def about_page():
    redir = admin_guard()
    if redir:
        return redir
    cfg = load_config()
    app_version = _get_version()
    return render_template(
        'admin_about.html',
        cfg=cfg,
        current_user=session.get('user'),
        logo_path=get_logo_path(),
        app_version=app_version,
        app_release_url=_get_release_url(app_version),
        git_commit=_get_git_commit(),
        license_exists=_license_exists(),
    )
