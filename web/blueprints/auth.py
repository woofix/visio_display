from flask import Blueprint, render_template, request, redirect, url_for, session
import secrets
from werkzeug.security import check_password_hash

from services.users_svc import load_users
from services.media_svc import get_logo_path
from services.i18n import _flash
from services.activity_svc import log_activity

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        users    = load_users()
        entry    = users.get(username, {})
        pwd_hash = entry.get('password', '') if isinstance(entry, dict) else entry
        if username in users and check_password_hash(pwd_hash, password):
            session.clear()
            session.permanent = True
            session['user'] = username
            session['_csrf_token'] = secrets.token_urlsafe(32)
            log_activity(username, 'login')
            return redirect(url_for('admin.admin_page'))
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
