# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import logging
import os
import re

from flask import session
from werkzeug.security import generate_password_hash, check_password_hash

from db import User, db
from services.queue_svc import get_redis

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_.-]{3,64}$')
MIN_PASSWORD_LENGTH = 10
LEGACY_PASSWORD_HASH_PLACEHOLDER = '__REDIS__'
LEGACY_PASSWORD_KEY_PREFIX = 'visio-display:user-password:'
LOGGER = logging.getLogger(__name__)


def normalize_username(value):
    return str(value or '').strip()


def is_valid_username(value):
    return bool(USERNAME_RE.fullmatch(normalize_username(value)))


def is_valid_password(value):
    return isinstance(value, str) and len(value.strip()) >= MIN_PASSWORD_LENGTH


def _json_list(raw_value):
    try:
        parsed = json.loads(raw_value or '[]')
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _legacy_password_key(username):
    return f'{LEGACY_PASSWORD_KEY_PREFIX}{normalize_username(username)}'


def set_user_password(username, password):
    user = get_user(username)
    if user is None:
        return False
    user.password_hash = generate_password_hash(password)
    db.session.commit()
    return True


def set_user_password_hash(username, password_hash):
    user = get_user(username)
    if user is None:
        return False
    user.password_hash = str(password_hash or '').strip()
    db.session.commit()
    return True


def _delete_legacy_password_hash(username):
    try:
        get_redis().delete(_legacy_password_key(username))
    except Exception:
        LOGGER.debug("Unable to remove legacy Redis password hash for %s", username, exc_info=True)


def verify_user_password(username, password):
    user = get_user(username)
    if user is None:
        return False
    password_hash = (user.password_hash or '').strip()
    if not password_hash or password_hash == LEGACY_PASSWORD_HASH_PLACEHOLDER:
        return False
    return check_password_hash(password_hash, password)


def get_user(username):
    normalized = normalize_username(username)
    if not normalized:
        return None
    return db.session.get(User, normalized)


def user_exists(username):
    return get_user(username) is not None


def create_user(username, password, *, superadmin=False, permissions=None, screens=None, theme='violet', language='fr'):
    normalized = normalize_username(username)
    if not normalized:
        raise ValueError('username is required')
    if user_exists(normalized):
        raise ValueError('user already exists')

    user = User(
        username=normalized,
        password_hash=generate_password_hash(password),
        superadmin=bool(superadmin),
        permissions=json.dumps(list(permissions or [])),
        screens=json.dumps(list(screens)) if screens is not None else None,
        theme=theme,
        language=language,
        must_change_password=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


def delete_user_account(username):
    user = get_user(username)
    if user is None:
        return False
    username = user.username
    db.session.delete(user)
    db.session.commit()
    _delete_legacy_password_hash(username)
    return True


def update_user_theme(username, theme):
    user = get_user(username)
    if user is None:
        return False
    user.theme = theme
    db.session.commit()
    return True


def update_user_language(username, language):
    user = get_user(username)
    if user is None:
        return False
    user.language = language
    db.session.commit()
    return True


def update_user_permissions(username, permissions):
    user = get_user(username)
    if user is None:
        return False
    user.permissions = json.dumps(list(permissions or []))
    db.session.commit()
    return True


def set_must_change_password(username, value: bool):
    user = get_user(username)
    if user is None:
        return False
    user.must_change_password = value
    db.session.commit()
    return True


def update_user_screens(username, screens):
    user = get_user(username)
    if user is None:
        return False
    user.screens = json.dumps(list(screens)) if screens is not None else None
    db.session.commit()
    return True


def _read_legacy_password_hash(username):
    try:
        raw = get_redis().get(_legacy_password_key(username))
    except Exception:
        LOGGER.exception("Unable to read legacy Redis password hash for %s", username)
        return ''
    if raw is None:
        return ''
    return raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)


def _migrate_password_hashes_from_redis():
    migrated_usernames = []
    for user in User.query.all():
        current_hash = (user.password_hash or '').strip()
        if current_hash != LEGACY_PASSWORD_HASH_PLACEHOLDER:
            continue
        legacy_hash = _read_legacy_password_hash(user.username)
        if not legacy_hash:
            continue
        user.password_hash = legacy_hash
        migrated_usernames.append(user.username)
    if migrated_usernames:
        db.session.commit()
        for username in migrated_usernames:
            _delete_legacy_password_hash(username)


def _repair_env_superadmin_password_if_legacy():
    username = os.environ.get('ADMIN_USER', '').strip()
    password = os.environ.get('ADMIN_PASSWORD', '').strip()
    if not username or not password:
        return
    user = get_user(username)
    if user is None or not user.superadmin:
        return
    current_hash = (user.password_hash or '').strip()
    if current_hash != LEGACY_PASSWORD_HASH_PLACEHOLDER:
        return
    user.password_hash = generate_password_hash(password)
    user.must_change_password = True
    db.session.commit()


def load_users():
    return {u.username: u.to_dict() for u in User.query.all()}


def save_users(users_dict):
    existing_usernames = {u.username for u in User.query.all()}
    incoming_usernames = set(users_dict.keys())

    for username in existing_usernames - incoming_usernames:
        User.query.filter_by(username=username).delete()
        _delete_legacy_password_hash(username)

    for username, entry in users_dict.items():
        if isinstance(entry, dict) and not entry.get('password_hash'):
            existing = db.session.get(User, username)
            if existing is not None:
                entry = {**entry, 'password_hash': existing.password_hash}
        db.session.merge(User.from_dict(username, entry))

    db.session.commit()


def init_users():
    if User.query.count() == 0:
        user = os.environ.get('ADMIN_USER', '').strip()
        pwd  = os.environ.get('ADMIN_PASSWORD', '').strip()
        if not user or not pwd:
            raise RuntimeError(
                "No user found. "
                "Set ADMIN_USER and ADMIN_PASSWORD for the first startup."
            )
        db.session.add(User(
            username=user,
            password_hash=generate_password_hash(pwd),
            superadmin=True,
            permissions='[]',
        ))
        db.session.commit()
    _migrate_password_hashes_from_redis()
    _repair_env_superadmin_password_if_legacy()


def is_admin():
    return get_user(session.get('user')) is not None


def is_superadmin():
    username = session.get('user')
    if not username:
        return False
    u = db.session.get(User, username)
    return u is not None and u.superadmin


def has_permission(perm):
    if is_superadmin():
        return True
    username = session.get('user')
    if not username:
        return False
    u = db.session.get(User, username)
    if u is None:
        return False
    if perm in _json_list(u.permissions):
        return True
    from services.rbac_svc import get_effective_permissions_for_user
    return perm in get_effective_permissions_for_user(username)


def has_screen_access(screen_name):
    if is_superadmin():
        return True
    username = session.get('user')
    if not username:
        return False
    u = db.session.get(User, username)
    if u is None:
        return False
    if u.screens is None:
        return True
    return screen_name in _json_list(u.screens)
