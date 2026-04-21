from flask import Blueprint, render_template, request, redirect, url_for, session
import secrets
import threading
import time
from services.users_svc import load_users, normalize_username, verify_user_password
from services.media_svc import get_logo_path
from services.i18n import _flash
from services.activity_svc import log_activity

bp = Blueprint('auth', __name__)

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5
_login_attempts = {}
_login_lock = threading.Lock()


def _client_ip():
    if request.access_route:
        return str(request.access_route[0]).strip()
    return str(request.remote_addr or '').strip()


def _prune_attempts(now):
    expired_keys = [
        key for key, entry in _login_attempts.items()
        if entry.get('blocked_until', 0) <= now and not entry.get('failures')
    ]
    for key in expired_keys:
        _login_attempts.pop(key, None)


def _login_is_blocked(username):
    now = time.time()
    key = f"{_client_ip()}::{username.casefold()}"
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


def _record_login_failure(username):
    now = time.time()
    key = f"{_client_ip()}::{username.casefold()}"
    with _login_lock:
        entry = _login_attempts.setdefault(key, {'failures': [], 'blocked_until': 0})
        failures = [ts for ts in entry['failures'] if now - ts < LOGIN_WINDOW_SECONDS]
        failures.append(now)
        entry['failures'] = failures
        if len(failures) >= LOGIN_MAX_FAILURES:
            entry['blocked_until'] = now + LOGIN_BLOCK_SECONDS
        _prune_attempts(now)


def _clear_login_failures(username):
    key = f"{_client_ip()}::{username.casefold()}"
    with _login_lock:
        _login_attempts.pop(key, None)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = normalize_username(request.form.get('username', ''))
        password = request.form.get('password', '')
        if _login_is_blocked(username):
            _flash('flash_login_rate_limited', 'error')
            return render_template('login.html', logo_path=get_logo_path()), 429
        users    = load_users()
        if username in users and verify_user_password(username, password):
            session.clear()
            session.permanent = True
            session['user'] = username
            session['_csrf_token'] = secrets.token_urlsafe(32)
            _clear_login_failures(username)
            log_activity(username, 'login')
            return redirect(url_for('admin.admin_page'))
        _record_login_failure(username)
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
