from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash

from services.users_svc import load_users
from services.media_svc import get_logo_path
from services.i18n import _flash

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
            session['user'] = username
            return redirect(url_for('admin.admin_page'))
        _flash('flash_wrong_credentials', 'error')
    return render_template('login.html', logo_path=get_logo_path())


@bp.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('auth.login'))
