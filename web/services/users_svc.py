import os
from flask import session
from werkzeug.security import generate_password_hash
from db import db, User


def load_users():
    return {u.username: u.to_dict() for u in User.query.all()}


def save_users(users_dict):
    existing_usernames = {u.username for u in User.query.all()}
    incoming_usernames = set(users_dict.keys())

    for username in existing_usernames - incoming_usernames:
        User.query.filter_by(username=username).delete()

    for username, entry in users_dict.items():
        db.session.merge(User.from_dict(username, entry))

    db.session.commit()


def init_users():
    if User.query.count() == 0:
        user = os.environ.get('ADMIN_USER', '').strip()
        pwd  = os.environ.get('ADMIN_PASSWORD', '').strip()
        if not user or not pwd:
            raise RuntimeError(
                "Aucun utilisateur trouvé. "
                "Définissez ADMIN_USER et ADMIN_PASSWORD pour le premier démarrage."
            )
        db.session.add(User(
            username=user,
            password_hash=generate_password_hash(pwd),
            superadmin=True,
            permissions='[]',
        ))
        db.session.commit()


def is_admin():
    return session.get('user') in {u.username for u in User.query.all()}


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
    import json
    return perm in json.loads(u.permissions or '[]')


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
    import json
    return screen_name in json.loads(u.screens)
