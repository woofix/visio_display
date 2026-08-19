# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import re
import json

from flask import Blueprint, jsonify, render_template, request, session

from blueprints.guards import admin_guard
from db import SearchIndex
from services.config_svc import load_config
from services.i18n import get_language
from services.media_svc import get_media_url
from services.search_engine_svc import rank_items
from services.search_index_svc import refresh_dynamic_search_index
from services.settings_sections import superadmin_nav_prefixes
from services.users_svc import is_superadmin, has_permission

bp = Blueprint('search', __name__)

MAX_PER_CATEGORY = 20

_URL_PERMISSION_MAP = [
    ('/admin/upload', ('upload',)),
    ('/admin/announcements', ('announcements', 'upload')),
    ('/admin/programming', ('schedule',)),
    ('/admin/settings/nettoyage-medias', ('cleanup',)),
    ('/admin/settings/alerte-prioritaire', ('priority_alert',)),
]

_URL_FEATURE_MAP = [
    ('/admin/upload', 'upload'),
    ('/admin/announcements', 'announcements'),
    ('/admin/campaigns', 'campaigns'),
    ('/admin/programming', 'schedule'),
    ('/admin/activity', 'activity'),
    ('/admin/settings/alerte-prioritaire', 'priority_alert'),
]

_URL_SUPERADMIN_PREFIXES = superadmin_nav_prefixes()

_CANONICAL_URL_ALIASES = {
    '/admin/settings#logo': '/admin/settings/logo',
    '/admin/settings#theme': '/admin/settings/theme',
    '/admin/settings#language': '/admin/settings/language',
    '/admin/settings#admins': '/admin/settings/comptes-permissions',
    '/admin/settings/admins': '/admin/settings/comptes-permissions',
    '/admin/settings#comptes-permissions': '/admin/settings/comptes-permissions',
    '/admin/settings#ajouter-compte': '/admin/settings/ajouter-compte',
    '/admin/settings#gestion-ecrans': '/admin/settings/gestion-ecrans',
    '/admin/settings#alerte-prioritaire': '/admin/settings/alerte-prioritaire',
    '/admin/settings#sauvegardes': '/admin/settings/sauvegardes',
    '/admin/settings#meteo': '/admin/settings/meteo',
    '/admin/settings#fonctionnalites': '/admin/settings/fonctionnalites',
    '/admin/settings#installation': '/admin/settings/installation',
    '/admin/settings#mot-de-passe': '/admin/settings/mot-de-passe',
    '/admin/superadmin': '/admin/settings/administration',
    '/admin/features': '/admin/settings/fonctionnalites',
}


def _canonical_url(url):
    wiki_hash_match = re.fullmatch(r'(/admin/wiki)#(s\d+)', url or '')
    if wiki_hash_match:
        return f'{wiki_hash_match.group(1)}/{wiki_hash_match.group(2)}'
    return _CANONICAL_URL_ALIASES.get(url, url)


def _is_url_available(url, *, superadmin=False, feature_enabled_fn=None):
    feature_enabled_fn = feature_enabled_fn or (lambda _feature: True)
    if not superadmin and any(url.startswith(prefix) for prefix in _URL_SUPERADMIN_PREFIXES):
        return False
    required_feature = next((feature for prefix, feature in _URL_FEATURE_MAP if url.startswith(prefix)), None)
    return not (required_feature and not feature_enabled_fn(required_feature))


def _split_restricted(pages, has_perm_fn, *, superadmin=False, feature_enabled_fn=None):
    accessible, restricted = [], []
    for page in pages:
        url = _canonical_url(page.get('url', ''))
        page = {**page, 'url': url}
        if not _is_url_available(url, superadmin=superadmin, feature_enabled_fn=feature_enabled_fn):
            continue
        required = next((p for prefix, p in _URL_PERMISSION_MAP if url.startswith(prefix)), None)
        if required and not any(has_perm_fn(permission) for permission in required):
            restricted.append({**page, 'required_perm': required[0]})
        else:
            accessible.append(page)
    return accessible, restricted


def _search_index(query, lang, category):
    """
    Load all rows for (category, lang), score in Python with the ranking engine.
    This avoids the imprecision of SQL ILIKE and adds accent/stem tolerance.
    """
    row_query = SearchIndex.query.filter(SearchIndex.category == category)
    if category in {'page', 'wiki'}:
        row_query = row_query.filter(SearchIndex.lang == lang)
    else:
        row_query = row_query.filter(SearchIndex.lang == 'all')
    rows = row_query.all()
    items = [
        {
            'title':       r.title,
            'description': r.description or '',
            'keywords':    r.keywords or '',
            'content':     r.content or '',
            'url':         _canonical_url(r.url),
            'desc':        r.description or '',
            'source_id':   r.source_id or '',
            'meta':        r.meta or '{}',
        }
        for r in rows
    ]
    ranked = rank_items(items, query)
    return [_format_index_item(it, category) for it in ranked[:MAX_PER_CATEGORY]]


def _parse_meta(raw_meta):
    try:
        value = json.loads(raw_meta or '{}')
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _format_index_item(item, category):
    meta = _parse_meta(item.get('meta'))
    if category == 'media':
        filename = meta.get('filename') or item.get('title', '')
        ext = meta.get('ext') or (filename.rsplit('.', 1)[-1].lower() if '.' in filename else '')
        return {
            'filename': filename,
            'ext': ext,
            'disabled': bool(meta.get('disabled')),
            'thumb_url': get_media_url(filename, context='admin') if filename else '',
        }
    if category == 'campaigns':
        return {
            'id': meta.get('id') or item.get('source_id', '').removeprefix('campaign:'),
            'name': meta.get('name') or item.get('title', ''),
            'enabled': bool(meta.get('enabled')),
            'archived': bool(meta.get('archived')),
            'start_date': meta.get('start_date') or '',
            'end_date': meta.get('end_date') or '',
        }
    if category == 'config':
        return {
            'type': meta.get('type') or '',
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'desc': item.get('desc', ''),
        }
    if category == 'users':
        return {
            'username': meta.get('username') or item.get('title', ''),
            'superadmin': bool(meta.get('superadmin')),
        }
    if category == 'activity':
        return meta
    return {'title': item['title'], 'url': item['url'], 'desc': item['desc']}


def _run_search(query, cfg, lang='fr', superadmin=False, has_perm_fn=None):
    if has_perm_fn is None:
        def has_perm_fn(p):
            return True

    refresh_dynamic_search_index(cfg)
    all_pages = _search_index(query, lang, 'page')
    from services.config_svc import is_feature_enabled
    accessible_pages, restricted_pages = _split_restricted(
        all_pages,
        has_perm_fn,
        superadmin=superadmin,
        feature_enabled_fn=is_feature_enabled,
    )

    results = {
        'pages':      accessible_pages,
        'wiki':       _search_index(query, lang, 'wiki'),
        'media':      _search_index(query, lang, 'media'),
        'campaigns':  _search_index(query, lang, 'campaigns'),
        'config':     [
            item for item in _search_index(query, lang, 'config')
            if _is_url_available(item.get('url', ''), superadmin=superadmin, feature_enabled_fn=is_feature_enabled)
        ],
        'activity':   _search_index(query, lang, 'activity'),
        'restricted': restricted_pages,
    }
    if superadmin:
        results['users'] = _search_index(query, lang, 'users')
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
        'pages': [],
        'wiki': [],
        'media': [],
        'campaigns': [],
        'config': [],
        'activity': [],
        'restricted': [],
        'users': [],
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
        return jsonify(
            {'pages': [], 'wiki': [], 'media': [], 'campaigns': [], 'config': [], 'activity': [], 'restricted': []}
        )
    cfg = load_config()
    sa = is_superadmin()
    lang = get_language()
    results = _run_search(q, cfg, lang=lang, superadmin=sa, has_perm_fn=has_permission)
    for category in results.values():
        for item in category:
            item.pop('thumb_url', None)
    return jsonify(results)
