# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import logging

from flask import flash, session
from translations import TRANSLATIONS


LOGGER = logging.getLogger(__name__)


def get_language(users_svc=None):
    """Return the language of the logged-in user, or the global language from config.json."""
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
    except RuntimeError:
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
            LOGGER.debug("Unable to format translation key: %s", key, exc_info=True)
    return val


def _flash(key, category='success', **kwargs):
    flash(_t(key, **kwargs), category)
