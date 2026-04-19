from flask import Blueprint, render_template, request, jsonify, session

from services.activity_svc import get_activity_log
from services.media_svc import get_logo_path
from services.users_svc import load_users
from blueprints.guards import admin_guard, feature_guard

bp = Blueprint('activity', __name__)


@bp.route('/admin/activity')
def activity_page():
    redir = admin_guard()
    if redir: return redir
    redir = feature_guard('activity')
    if redir: return redir
    logs  = get_activity_log(limit=500)
    users = load_users()
    return render_template('admin_activity.html',
        logs=logs,
        users=list(users.keys()),
        current_user=session.get('user'),
        logo_path=get_logo_path())


@bp.route('/api/activity')
def api_activity():
    redir = admin_guard()
    if redir: return jsonify({"error": "unauthorized"}), 401
    limit = min(int(request.args.get('limit', 200)), 1000)
    return jsonify(get_activity_log(limit=limit))
