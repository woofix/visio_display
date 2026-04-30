# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os
import re

from flask import session
from werkzeug.security import generate_password_hash, check_password_hash

from db import User, db
from services.queue_svc import get_redis

USERNAME_RE = re.compile(r'^[a-zA-Z0-9_.-]{3,64}$')
MIN_PASSWORD_LENGTH = 10
PASSWORD_HASH_PLACEHOLDER = '__REDIS__'
PASSWORD_KEY_PREFIX = 'visio-display:user-password:'


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


def _password_key(username):
    return f'{PASSWORD_KEY_PREFIX}{normalize_username(username)}'


def get_password_hash(username):
    raw = get_redis().get(_password_key(username))
    if raw is None:
        return ''
    return raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)


def set_user_password(username, password):
    get_redis().set(_password_key(username), generate_password_hash(password))


def set_user_password_hash(username, password_hash):
    get_redis().set(_password_key(username), password_hash)


def delete_user_password(username):
    get_redis().delete(_password_key(username))


def verify_user_password(username, password):
    password_hash = get_password_hash(username)
    return bool(password_hash) and check_password_hash(password_hash, password)


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
        password_hash=PASSWORD_HASH_PLACEHOLDER,
        superadmin=bool(superadmin),
        permissions=json.dumps(list(permissions or [])),
        screens=json.dumps(list(screens)) if screens is not None else None,
        theme=theme,
        language=language,
        must_change_password=True,
    )
    db.session.add(user)
    db.session.commit()
    set_user_password(normalized, password)
    return user


def delete_user_account(username):
    user = get_user(username)
    if user is None:
        return False
    db.session.delete(user)
    db.session.commit()
    delete_user_password(user.username)
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


def _migrate_password_hashes_to_redis():
    changed = False
    for user in User.query.all():
        current_hash = (user.password_hash or '').strip()
        if current_hash and current_hash != PASSWORD_HASH_PLACEHOLDER and not get_password_hash(user.username):
            set_user_password_hash(user.username, current_hash)
        if current_hash != PASSWORD_HASH_PLACEHOLDER:
            user.password_hash = PASSWORD_HASH_PLACEHOLDER
            changed = True
    if changed:
        db.session.commit()


def load_users():
    return {u.username: u.to_dict() for u in User.query.all()}


def save_users(users_dict):
    existing_usernames = {u.username for u in User.query.all()}
    incoming_usernames = set(users_dict.keys())

    for username in existing_usernames - incoming_usernames:
        User.query.filter_by(username=username).delete()
        delete_user_password(username)

    for username, entry in users_dict.items():
        db.session.merge(User.from_dict(username, entry))

    db.session.commit()


def init_users():
    get_redis().ping()
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
            password_hash=PASSWORD_HASH_PLACEHOLDER,
            superadmin=True,
            permissions='[]',
        ))
        db.session.commit()
        set_user_password(user, pwd)
    _migrate_password_hashes_to_redis()


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
