# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, render_template, request, redirect, url_for, session
import logging
import os
import secrets
from redis import Redis

from services.users_svc import bump_session_epoch, get_session_epoch, normalize_username, verify_user_password
from services.media_svc import get_logo_path
from services.i18n import _flash
from services.activity_svc import log_activity

bp = Blueprint('auth', __name__)
LOGGER = logging.getLogger(__name__)

LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')

_redis: Redis = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL)
    return _redis


def _client_ip():
    return str(request.remote_addr or '').strip()


def _login_rate_limit_key(username, ip=None):
    return f"visio-display:rate-limit:login:{(ip if ip is not None else _client_ip())}::{username.casefold()}"


def _login_blocked_key(username, ip=None):
    return f"visio-display:rate-limit:login:blocked:{(ip if ip is not None else _client_ip())}::{username.casefold()}"


def _login_is_blocked(username, ip=None):
    r = get_redis()
    blocked_key = _login_blocked_key(username, ip)
    if r.exists(blocked_key):
        return True
    key = _login_rate_limit_key(username, ip)
    count = r.get(key)
    if count is not None and int(count) >= LOGIN_MAX_FAILURES:
        ttl = r.ttl(key)
        r.setex(blocked_key, max(ttl, LOGIN_BLOCK_SECONDS), '1')
        return True
    return False


def _record_login_failure(username, ip=None):
    r = get_redis()
    key = _login_rate_limit_key(username, ip)
    count = r.incr(key)
    if count == 1:
        r.expire(key, LOGIN_WINDOW_SECONDS)
    if int(count) >= LOGIN_MAX_FAILURES:
        r.setex(_login_blocked_key(username, ip), LOGIN_BLOCK_SECONDS, '1')


def _clear_login_failures(username, ip=None):
    r = get_redis()
    r.delete(_login_rate_limit_key(username, ip))
    r.delete(_login_blocked_key(username, ip))


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
        if verify_user_password(username, password):
            session.clear()
            session.permanent = True
            if login_language in {'fr', 'en'}:
                session['login_language'] = login_language
            session['user'] = username
            session['_csrf_token'] = secrets.token_urlsafe(32)
            session['_session_epoch'] = get_session_epoch(username)
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
        bump_session_epoch(user)
        log_activity(user, 'logout')
    return redirect(url_for('auth.login'))
