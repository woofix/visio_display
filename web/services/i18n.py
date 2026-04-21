from flask import session, flash
from translations import TRANSLATIONS


def get_language(users_svc=None):
    """Retourne la langue de l'utilisateur connecté, sinon la langue globale de config.json."""
    try:
        from services.users_svc import load_users
        from services.config_svc import load_config
        username = session.get('user')
        if username:
            users = load_users()
            entry = users.get(username, {})
            if isinstance(entry, dict) and 'language' in entry:
                return entry['language']
        cfg = load_config()
        return cfg.get('language', 'fr')
    except Exception:
        return 'fr'


def _trans(lang=None):
    if lang is None:
        lang = get_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS['fr'])


def _t(key, lang=None, **kwargs):
    trans = _trans(lang)
    val = trans.get(key, TRANSLATIONS['fr'].get(key, key))
    if kwargs:
        try:
            val = val.format(**kwargs)
        except (KeyError, ValueError):
            pass
    return val


def _flash(key, category='success', **kwargs):
    flash(_t(key, **kwargs), category)
