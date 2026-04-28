# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import re

from flask import Blueprint, jsonify, render_template, request, session

from blueprints.guards import admin_guard
from db import ActivityLog, SearchIndex, db
from services.campaign_svc import get_campaigns
from services.config_svc import load_config
from services.i18n import get_language
from services.media_svc import get_all_media, get_media_url, is_media_disabled
from services.search_engine_svc import normalize, parse_query, rank_items
from services.users_svc import is_superadmin, load_users, has_permission

bp = Blueprint('search', __name__)

MAX_PER_CATEGORY = 20

_URL_PERMISSION_MAP = [
    ('/admin/upload', 'upload'),
]


def _split_restricted(pages, has_perm_fn):
    accessible, restricted = [], []
    for page in pages:
        url = page.get('url', '')
        required = next((p for prefix, p in _URL_PERMISSION_MAP if url.startswith(prefix)), None)
        if required and not has_perm_fn(required):
            restricted.append({**page, 'required_perm': required})
        else:
            accessible.append(page)
    return accessible, restricted


def _search_index(query, lang, category):
    """
    Load all rows for (category, lang), score in Python with the ranking engine.
    This avoids the imprecision of SQL ILIKE and adds accent/stem tolerance.
    """
    rows = (
        SearchIndex.query
        .filter(SearchIndex.category == category, SearchIndex.lang == lang)
        .all()
    )
    items = [
        {
            'title':       r.title,
            'description': r.description or '',
            'keywords':    r.keywords or '',
            'url':         r.url,
            'desc':        r.description or '',
        }
        for r in rows
    ]
    ranked = rank_items(items, query)
    return [{'title': it['title'], 'url': it['url'], 'desc': it['desc']}
            for it in ranked[:MAX_PER_CATEGORY]]


def _media_keywords(filename):
    """Split filename stem on separators to improve token matching."""
    stem = filename.rsplit('.', 1)[0] if '.' in filename else filename
    return ' '.join(re.split(r'[_\-\s\.]+', stem))


def _search_media(query, cfg):
    items = []
    for filename in get_all_media(cfg):
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        items.append({
            'title':       filename,
            'keywords':    _media_keywords(filename) + ' ' + ext,
            'description': '',
            # display fields — passed through untouched
            'filename':    filename,
            'ext':         ext,
            'disabled':    is_media_disabled(filename, cfg),
            'thumb_url':   get_media_url(filename, context='admin'),
        })
    ranked = rank_items(items, query)
    return ranked[:MAX_PER_CATEGORY]


def _campaign_item(campaign):
    return {
        'title':       campaign.get('name', ''),
        'description': f"{campaign.get('start_date', '')} {campaign.get('end_date', '')}".strip(),
        'keywords':    ' '.join(filter(None, [
            campaign.get('created_by', ''),
            ' '.join(campaign.get('screens', [])),
            ' '.join(campaign.get('groups', [])),
            ' '.join(campaign.get('media', [])),
        ])),
        # display fields
        'id':          campaign['id'],
        'name':        campaign.get('name', ''),
        'enabled':     campaign.get('enabled', False),
        'archived':    campaign.get('archived', False),
        'start_date':  campaign.get('start_date', ''),
        'end_date':    campaign.get('end_date', ''),
    }


def _search_campaigns(query, cfg):
    items = [_campaign_item(c) for c in get_campaigns(cfg)]
    ranked = rank_items(items, query)
    return [
        {
            'id':         it['id'],
            'name':       it['name'],
            'enabled':    it['enabled'],
            'archived':   it['archived'],
            'start_date': it['start_date'],
            'end_date':   it['end_date'],
        }
        for it in ranked[:MAX_PER_CATEGORY]
    ]


def _search_activity(query):
    """
    Pre-filter in DB using normalized query words (broad ILIKE), then
    score and rank results in Python for precision.
    """
    groups = parse_query(query)
    if not groups:
        return []

    # Build one ILIKE condition per query word (OR across words, AND across fields)
    conditions = []
    for qsg in groups:
        word_conds = []
        for stem in qsg:
            pat = f'%{stem}%'
            word_conds.extend([
                ActivityLog.username.ilike(pat),
                ActivityLog.action.ilike(pat),
                ActivityLog.filename.ilike(pat),
                ActivityLog.details.ilike(pat),
            ])
        conditions.append(db.or_(*word_conds))

    logs = (
        ActivityLog.query
        .filter(db.and_(*conditions))
        .order_by(ActivityLog.timestamp.desc())
        .limit(MAX_PER_CATEGORY * 5)
        .all()
    )

    items = [
        {
            'title':       log.action,
            'description': f"{log.username} {log.filename or ''}".strip(),
            'keywords':    log.details or '',
            '_log':        log.to_dict(),
        }
        for log in logs
    ]
    ranked = rank_items(items, query)
    return [it['_log'] for it in ranked[:MAX_PER_CATEGORY]]


def _config_items(cfg):
    items = []
    for screen_name in cfg.get('screens', {}).keys():
        items.append({
            'title':       screen_name,
            'description': "Écran d'affichage",
            'keywords':    'ecran display moniteur affichage kiosk',
            'type':        'screen',
            'url':         '/admin/settings#gestion-ecrans',
            'desc':        "Écran d'affichage",
        })
    groups_seen = set()
    for groups in cfg.get('groups', {}).values():
        for group in (groups if isinstance(groups, list) else []):
            if group and group not in groups_seen:
                groups_seen.add(group)
                items.append({
                    'title':       group,
                    'description': 'Groupe de médias',
                    'keywords':    'groupe tag media organiser',
                    'type':        'group',
                    'url':         '/admin/media',
                    'desc':        'Groupe de médias',
                })
    app_name = cfg.get('app_name', '')
    if app_name:
        items.append({
            'title':       app_name,
            'description': "Nom de l'application",
            'keywords':    'application nom configuration',
            'type':        'app',
            'url':         '/admin/settings#application',
            'desc':        "Nom de l'application",
        })
    return items


def _search_config(query, cfg):
    items = _config_items(cfg)
    ranked = rank_items(items, query)
    return [
        {'type': it['type'], 'title': it['title'], 'url': it['url'], 'desc': it['desc']}
        for it in ranked[:MAX_PER_CATEGORY]
    ]


def _search_users(query):
    items = []
    for username, info in load_users().items():
        items.append({
            'title':       username,
            'description': 'super-admin' if info.get('superadmin') else 'administrateur',
            'keywords':    'utilisateur compte admin',
            '_username':   username,
            '_superadmin': info.get('superadmin', False),
        })
    ranked = rank_items(items, query)
    return [
        {'username': it['_username'], 'superadmin': it['_superadmin']}
        for it in ranked[:MAX_PER_CATEGORY]
    ]


def _run_search(query, cfg, lang='fr', superadmin=False, has_perm_fn=None):
    if has_perm_fn is None:
        has_perm_fn = lambda p: True

    all_pages = _search_index(query, lang, 'page')
    accessible_pages, restricted_pages = _split_restricted(all_pages, has_perm_fn)

    results = {
        'pages':      accessible_pages,
        'wiki':       _search_index(query, lang, 'wiki'),
        'media':      _search_media(query, cfg),
        'campaigns':  _search_campaigns(query, cfg),
        'config':     _search_config(query, cfg),
        'activity':   _search_activity(query),
        'restricted': restricted_pages,
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
    results = _run_search(q, cfg, lang=lang, superadmin=sa, has_perm_fn=has_permission) if q else {
        'pages': [], 'wiki': [], 'media': [], 'campaigns': [], 'config': [], 'activity': [], 'restricted': [], 'users': [],
    }
    total = sum(len(v) for k, v in results.items() if k != 'restricted')
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
        return jsonify({'pages': [], 'wiki': [], 'media': [], 'campaigns': [], 'config': [], 'activity': [], 'restricted': []})
    cfg = load_config()
    sa = is_superadmin()
    lang = get_language()
    results = _run_search(q, cfg, lang=lang, superadmin=sa, has_perm_fn=has_permission)
    for category in results.values():
        for item in category:
            item.pop('thumb_url', None)
    return jsonify(results)
