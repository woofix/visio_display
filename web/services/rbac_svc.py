# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import re

from db import db, Role, RolePermission, UserRole
from constants import ALL_PERMISSIONS

_ALL_PERM_KEYS = [p for p, _ in ALL_PERMISSIONS]
_ROLE_NAME_RE  = re.compile(r'^[a-z0-9_-]{2,64}$')

_DEFAULT_ROLES = [
    {
        'name':         'admin',
        'display_name': 'Administrator',
        'description':  'Full access to all features',
        'is_system':    True,
        'permissions':  _ALL_PERM_KEYS,
    },
    {
        'name':         'editor',
        'display_name': 'Editor',
        'description':  'Can add, delete and edit media',
        'is_system':    False,
        'permissions':  ['upload', 'announcements', 'menus', 'delete', 'reorder', 'toggle', 'duration'],
    },
    {
        'name':         'viewer',
        'display_name': 'Viewer',
        'description':  'Read-only access to the dashboard',
        'is_system':    False,
        'permissions':  [],
    },
]


def is_valid_role_name(name):
    return bool(_ROLE_NAME_RE.fullmatch(str(name or '').strip()))


def get_all_roles():
    return Role.query.order_by(Role.id).all()


def get_role(role_id):
    return db.session.get(Role, role_id)


def get_role_by_name(name):
    return Role.query.filter_by(name=str(name or '').strip()).first()


def create_role(name, display_name, description=None, permissions=None):
    name = str(name or '').strip()
    if not is_valid_role_name(name):
        raise ValueError('invalid_role_name')
    if Role.query.filter_by(name=name).first():
        raise ValueError('role_exists')
    role = Role(name=name, display_name=display_name.strip(), description=(description or '').strip() or None, is_system=False)
    db.session.add(role)
    db.session.flush()
    _apply_permissions(role.id, permissions or [])
    db.session.commit()
    return role


def update_role(role_id, display_name, description=None):
    role = db.session.get(Role, role_id)
    if role is None:
        raise ValueError('role_not_found')
    role.display_name = display_name.strip()
    role.description  = (description or '').strip() or None
    db.session.commit()
    return role


def delete_role(role_id):
    role = db.session.get(Role, role_id)
    if role is None:
        raise ValueError('role_not_found')
    if role.is_system:
        raise ValueError('role_system_protected')
    db.session.delete(role)
    db.session.commit()


def set_role_permissions(role_id, permissions):
    role = db.session.get(Role, role_id)
    if role is None:
        raise ValueError('role_not_found')
    _apply_permissions(role_id, permissions)
    db.session.commit()


def _apply_permissions(role_id, permissions):
    RolePermission.query.filter_by(role_id=role_id).delete()
    valid = set(_ALL_PERM_KEYS)
    for perm in (permissions or []):
        if perm in valid:
            db.session.add(RolePermission(role_id=role_id, permission=perm))


def get_user_roles(username):
    rows = UserRole.query.filter_by(username=username).all()
    if not rows:
        return []
    ids = [r.role_id for r in rows]
    return Role.query.filter(Role.id.in_(ids)).order_by(Role.id).all()


def set_user_roles(username, role_ids):
    UserRole.query.filter_by(username=username).delete()
    for rid in role_ids:
        if db.session.get(Role, rid) is not None:
            db.session.add(UserRole(username=username, role_id=rid))
    db.session.commit()


def get_effective_permissions_for_user(username):
    """Returns the set of all permissions granted through roles."""
    rows = UserRole.query.filter_by(username=username).all()
    if not rows:
        return set()
    ids = [r.role_id for r in rows]
    perms = RolePermission.query.filter(RolePermission.role_id.in_(ids)).all()
    return {p.permission for p in perms}


def init_rbac():
    for role_def in _DEFAULT_ROLES:
        role = Role.query.filter_by(name=role_def['name']).first()
        if role is None:
            role = Role(
                name=role_def['name'],
                display_name=role_def['display_name'],
                description=role_def['description'],
                is_system=role_def['is_system'],
            )
            db.session.add(role)
            db.session.flush()
            for perm in role_def['permissions']:
                db.session.add(RolePermission(role_id=role.id, permission=perm))
        elif role.name == 'admin' and role.is_system:
            existing = {p.permission for p in RolePermission.query.filter_by(role_id=role.id).all()}
            for perm in role_def['permissions']:
                if perm not in existing:
                    db.session.add(RolePermission(role_id=role.id, permission=perm))
    db.session.commit()
