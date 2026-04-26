# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

from flask import Blueprint, jsonify, render_template, request, session

from blueprints.guards import admin_guard
from db import ActivityLog
from services.campaign_svc import get_campaigns
from services.config_svc import load_config
from services.media_svc import get_all_media, get_media_url, is_media_disabled
from services.users_svc import is_superadmin, load_users

bp = Blueprint('search', __name__)

MAX_PER_CATEGORY = 20

# Pages statiques du site avec mots-clés pour la recherche
SITE_PAGES = [
    {
        'title': "Tableau de bord",
        'url': '/admin',
        'desc': "Vue d'ensemble, statistiques, médias actifs",
        'keywords': 'tableau bord dashboard overview vue ensemble statistiques accueil home',
    },
    {
        'title': "Médiathèque",
        'url': '/admin/media',
        'desc': "Gestion des médias, planification, désactivation",
        'keywords': 'médiathèque médias images photos vidéos fichiers bibliothèque galerie désactiver planifier',
    },
    {
        'title': "Campagnes",
        'url': '/admin/campaigns',
        'desc': "Créer et gérer les campagnes de diffusion",
        'keywords': 'campagnes campagne diffusion programmation priorité écrans groupes créer modifier',
    },
    {
        'title': "Plages de diffusion",
        'url': '/admin/programming',
        'desc': "Programmer les plages horaires de diffusion",
        'keywords': 'plages diffusion programmation horaires planning semaine jours calendrier créneau',
    },
    {
        'title': "Ajouter des médias",
        'url': '/admin/upload',
        'desc': "Importer de nouveaux fichiers image ou vidéo",
        'keywords': 'upload ajouter médias importer télécharger fichiers uploader jpg png mp4 pdf',
    },
    {
        'title': "File d'encodage",
        'url': '/admin/upload',
        'desc': "File d'attente pour la compression vidéo",
        'keywords': "file encodage compression vidéo convertir encoder queue attente compress",
    },
    {
        'title': "Journal d'activité",
        'url': '/admin/activity',
        'desc': "Historique de toutes les actions effectuées",
        'keywords': 'activité journal logs historique événements audit actions utilisateurs traçabilité',
    },
    {
        'title': "Paramètres",
        'url': '/admin/settings',
        'desc': "Configuration générale de l'application",
        'keywords': 'paramètres configuration settings application général réglages options',
    },
    {
        'title': "Logo",
        'url': '/admin/settings#logo',
        'desc': "Changer le logo affiché sur les écrans",
        'keywords': 'logo image marque brand personnalisation changer remplacer',
    },
    {
        'title': "Thème et apparence",
        'url': '/admin/settings#theme',
        'desc': "Choisir le thème de couleur de l'interface",
        'keywords': 'thème couleurs apparence design interface violet bleu vert orange sombre clair',
    },
    {
        'title': "Langue",
        'url': '/admin/settings#language',
        'desc': "Choisir la langue de l'interface",
        'keywords': 'langue language français anglais traduction interface fr en',
    },
    {
        'title': "Utilisateurs et comptes",
        'url': '/admin/settings#admins',
        'desc': "Gérer les comptes administrateurs et leurs droits",
        'keywords': 'utilisateurs comptes administrateurs permissions droits accès mot de passe compte créer supprimer',
    },
    {
        'title': "Écrans d'affichage",
        'url': '/admin/settings#gestion-ecrans',
        'desc': "Ajouter et gérer les écrans connectés",
        'keywords': 'écrans displays moniteurs affichage kiosk téléviseurs ajouter supprimer halo couleur',
    },
    {
        'title': "Alerte prioritaire",
        'url': '/admin/settings#alerte-prioritaire',
        'desc': "Afficher un message d'urgence sur tous les écrans",
        'keywords': 'alerte prioritaire urgence message priorité interrompre diffusion',
    },
    {
        'title': "Sauvegardes",
        'url': '/admin/settings#sauvegardes',
        'desc': "Créer et restaurer des sauvegardes",
        'keywords': 'sauvegardes backup restaurer restore archive données exporter importer',
    },
    {
        'title': "Météo et éphéméride",
        'url': '/admin/settings#meteo',
        'desc': "Configuration météo et calendrier des éphémérides",
        'keywords': 'météo éphéméride calendrier événements saison prévisions ville timezone',
    },
    {
        'title': "Fonctionnalités",
        'url': '/admin/settings#fonctionnalites',
        'desc': "Activer ou désactiver les modules du site",
        'keywords': 'fonctionnalités features activer désactiver modules options upload vidéo compression groupes',
    },
    {
        'title': "Administration clients",
        'url': '/admin/settings#installation',
        'desc': "Déployer et gérer les clients distants",
        'keywords': 'clients installation déploiement raspberry pi kiosk mise à jour remote',
    },
    {
        'title': "Changer mon mot de passe",
        'url': '/admin/settings#mot-de-passe',
        'desc': "Modifier le mot de passe du compte actuel",
        'keywords': 'mot de passe password changer modifier sécurité compte',
    },
    {
        'title': "Documentation / Wiki",
        'url': '/admin/wiki',
        'desc': "Aide, guide d'utilisation et documentation",
        'keywords': 'wiki documentation aide guide manuel help tutoriel utilisation',
    },
]


def _search_pages(query):
    q = query.casefold()
    results = []
    for page in SITE_PAGES:
        haystack = (page['title'] + ' ' + page['desc'] + ' ' + page['keywords']).casefold()
        if q in haystack:
            results.append(page)
    return results


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
    # Écrans
    for screen_name in cfg.get('screens', {}).keys():
        if q in screen_name.casefold():
            results.append({
                'type': 'screen',
                'title': screen_name,
                'url': '/admin/settings#gestion-ecrans',
                'desc': "Écran d'affichage",
            })
    # Groupes
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
    # Nom de l'application
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


def _run_search(query, cfg, superadmin=False):
    results = {
        'pages': _search_pages(query),
        'media': _search_media(query, cfg),
        'campaigns': _search_campaigns(query, cfg),
        'config': _search_config(query, cfg),
        'activity': _search_activity(query),
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
    results = _run_search(q, cfg, superadmin=sa) if q else {
        'pages': [], 'media': [], 'campaigns': [], 'config': [], 'activity': [], 'users': [],
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
        return jsonify({'pages': [], 'media': [], 'campaigns': [], 'config': [], 'activity': []})
    cfg = load_config()
    sa = is_superadmin()
    results = _run_search(q, cfg, superadmin=sa)
    for category in results.values():
        for item in category:
            item.pop('thumb_url', None)
    return jsonify(results)
