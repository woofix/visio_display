# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import Blueprint, jsonify, render_template, request, session

from blueprints.guards import admin_guard
from db import ActivityLog, SearchIndex, db
from services.campaign_svc import get_campaigns
from services.config_svc import load_config
from services.i18n import get_language
from services.media_svc import get_all_media, get_media_url, is_media_disabled
from services.users_svc import is_superadmin, load_users

bp = Blueprint('search', __name__)

MAX_PER_CATEGORY = 20


def _search_index(query, lang, category):
    q = f'%{query}%'
    rows = (
        SearchIndex.query
        .filter(
            SearchIndex.category == category,
            SearchIndex.lang == lang,
            db.or_(
                SearchIndex.title.ilike(q),
                SearchIndex.description.ilike(q),
                SearchIndex.keywords.ilike(q),
            )
        )
        .limit(MAX_PER_CATEGORY)
        .all()
    )
    return [{'title': r.title, 'url': r.url, 'desc': r.description} for r in rows]


def _search_media(query, cfg):
    q = query.casefold()
    results = []
    for filename in get_all_media(cfg):
        if q in filename.casefold():
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            results.append({
                'filename': filename,
                'ext': ext,
                'disabled': is_media_disabled(filename, cfg),
                'thumb_url': get_media_url(filename, context='admin'),
            })
            if len(results) >= MAX_PER_CATEGORY:
                break
    return results


def _campaign_searchable_text(campaign):
    parts = [
        campaign.get('name', ''),
        campaign.get('created_by', ''),
        ' '.join(campaign.get('screens', [])),
        ' '.join(campaign.get('groups', [])),
        ' '.join(campaign.get('media', [])),
        campaign.get('start_date', ''),
        campaign.get('end_date', ''),
    ]
    return ' '.join(p for p in parts if p).casefold()


def _search_campaigns(query, cfg):
    q = query.casefold()
    results = []
    for campaign in get_campaigns(cfg):
        if q in _campaign_searchable_text(campaign):
            results.append({
                'id': campaign['id'],
                'name': campaign.get('name', ''),
                'enabled': campaign.get('enabled', False),
                'archived': campaign.get('archived', False),
                'start_date': campaign.get('start_date', ''),
                'end_date': campaign.get('end_date', ''),
            })
            if len(results) >= MAX_PER_CATEGORY:
                break
    return results


def _search_activity(query):
    q = f'%{query}%'
    logs = (
        ActivityLog.query
        .filter(
            ActivityLog.username.ilike(q) |
            ActivityLog.action.ilike(q) |
            ActivityLog.filename.ilike(q) |
            ActivityLog.details.ilike(q)
        )
        .order_by(ActivityLog.timestamp.desc())
        .limit(MAX_PER_CATEGORY)
        .all()
    )
    return [log.to_dict() for log in logs]


def _search_config(query, cfg):
    q = query.casefold()
    results = []
    for screen_name in cfg.get('screens', {}).keys():
        if q in screen_name.casefold():
            results.append({
                'type': 'screen',
                'title': screen_name,
                'url': '/admin/settings#gestion-ecrans',
                'desc': "Écran d'affichage",
            })
    groups_seen = set()
    for groups in cfg.get('groups', {}).values():
        for group in (groups if isinstance(groups, list) else []):
            if group and group not in groups_seen:
                groups_seen.add(group)
                if q in group.casefold():
                    results.append({
                        'type': 'group',
                        'title': group,
                        'url': '/admin/media',
                        'desc': "Groupe de médias",
                    })
    app_name = cfg.get('app_name', '')
    if app_name and q in app_name.casefold():
        results.append({
            'type': 'app',
            'title': app_name,
            'url': '/admin/settings#application',
            'desc': "Nom de l'application",
        })
    return results[:MAX_PER_CATEGORY]


def _search_users(query):
    q = query.casefold()
    results = []
    for username, info in load_users().items():
        if q in username.casefold():
            results.append({
                'username': username,
                'superadmin': info.get('superadmin', False),
            })
            if len(results) >= MAX_PER_CATEGORY:
                break
    return results


def _run_search(query, cfg, lang='fr', superadmin=False):
    results = {
        'pages':     _search_index(query, lang, 'page'),
        'wiki':      _search_index(query, lang, 'wiki'),
        'media':     _search_media(query, cfg),
        'campaigns': _search_campaigns(query, cfg),
        'config':    _search_config(query, cfg),
        'activity':  _search_activity(query),
    }
    if superadmin:
        results['users'] = _search_users(query)
    return results


@bp.route('/admin/search')
def admin_search_page():
    redir = admin_guard()
    if redir:
        return redir
    q = request.args.get('q', '').strip()
    cfg = load_config()
    sa = is_superadmin()
    lang = get_language()
    results = _run_search(q, cfg, lang=lang, superadmin=sa) if q else {
        'pages': [], 'wiki': [], 'media': [], 'campaigns': [], 'config': [], 'activity': [], 'users': [],
    }
    total = sum(len(v) for v in results.values())
    return render_template(
        'admin_search.html',
        query=q,
        results=results,
        total=total,
        current_user=session.get('user'),
        is_superadmin=sa,
    )


@bp.route('/api/search')
def api_search():
    redir = admin_guard()
    if redir:
        return jsonify({'error': 'unauthorized'}), 401
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'pages': [], 'wiki': [], 'media': [], 'campaigns': [], 'config': [], 'activity': []})
    cfg = load_config()
    sa = is_superadmin()
    lang = get_language()
    results = _run_search(q, cfg, lang=lang, superadmin=sa)
    for category in results.values():
        for item in category:
            item.pop('thumb_url', None)
    return jsonify(results)
