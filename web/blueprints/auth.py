# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, render_template, request, redirect, url_for, session
import logging
import secrets
import threading
import time
from services.users_svc import load_users, normalize_username, verify_user_password
from services.media_svc import get_logo_path
from services.i18n import _flash
from services.activity_svc import log_activity

bp = Blueprint('auth', __name__)
LOGGER = logging.getLogger(__name__)

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5
_login_attempts = {}
_login_lock = threading.Lock()


def _client_ip():
    return str(request.remote_addr or '').strip()


def _prune_attempts(now):
    expired_keys = [
        key for key, entry in _login_attempts.items()
        if entry.get('blocked_until', 0) <= now and not entry.get('failures')
    ]
    for key in expired_keys:
        _login_attempts.pop(key, None)


def _login_attempt_key(username, ip=None):
    return f"{(ip if ip is not None else _client_ip())}::{username.casefold()}"


def _login_is_blocked(username, ip=None):
    now = time.time()
    key = _login_attempt_key(username, ip)
    with _login_lock:
        entry = _login_attempts.get(key)
        if not entry:
            return False
        if entry.get('blocked_until', 0) > now:
            return True
        failures = [ts for ts in entry.get('failures', []) if now - ts < LOGIN_WINDOW_SECONDS]
        entry['failures'] = failures
        entry['blocked_until'] = 0
        if not failures:
            _login_attempts.pop(key, None)
        _prune_attempts(now)
    return False


def _record_login_failure(username, ip=None):
    now = time.time()
    key = _login_attempt_key(username, ip)
    with _login_lock:
        entry = _login_attempts.setdefault(key, {'failures': [], 'blocked_until': 0})
        failures = [ts for ts in entry['failures'] if now - ts < LOGIN_WINDOW_SECONDS]
        failures.append(now)
        entry['failures'] = failures
        if len(failures) >= LOGIN_MAX_FAILURES:
            entry['blocked_until'] = now + LOGIN_BLOCK_SECONDS
        _prune_attempts(now)


def _clear_login_failures(username, ip=None):
    key = _login_attempt_key(username, ip)
    with _login_lock:
        _login_attempts.pop(key, None)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    requested_lang = request.values.get('lang', '').strip().lower()
    if requested_lang in {'fr', 'en'}:
        session['login_language'] = requested_lang
    if request.method == 'POST':
        username = normalize_username(request.form.get('username', ''))
        password = request.form.get('password', '')
        login_language = session.get('login_language')
        ip = _client_ip()
        if _login_is_blocked(username, ip):
            LOGGER.warning("Blocked login attempt for user '%s' from %s: rate limit exceeded", username, ip)
            log_activity(username, 'login', details=f'rate_limited ip={ip}')
            _flash('flash_login_rate_limited', 'error')
            return render_template('login.html', logo_path=get_logo_path()), 429
        users = load_users()
        if username in users and verify_user_password(username, password):
            session.clear()
            session.permanent = True
            if login_language in {'fr', 'en'}:
                session['login_language'] = login_language
            session['user'] = username
            session['_csrf_token'] = secrets.token_urlsafe(32)
            _clear_login_failures(username, ip)
            log_activity(username, 'login')
            from services.users_svc import get_user as _get_user
            _user_obj = _get_user(username)
            if _user_obj and _user_obj.must_change_password:
                _flash('flash_must_change_password', 'warning')
            return redirect(url_for('admin.admin_page'))
        _record_login_failure(username, ip)
        _flash('flash_wrong_credentials', 'error')
    return render_template('login.html', logo_path=get_logo_path())


@bp.route('/logout', methods=['GET', 'POST'])
def logout():
    if request.method != 'POST':
        if session.get('user'):
            return redirect(url_for('admin.admin_page'))
        return redirect(url_for('auth.login'))
    user = session.get('user')
    session.clear()
    if user:
        log_activity(user, 'logout')
    return redirect(url_for('auth.login'))
