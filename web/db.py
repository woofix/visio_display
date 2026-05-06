# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
LEGACY_PASSWORD_HASH_PLACEHOLDER = '__REDIS__'


class Role(db.Model):
    __tablename__ = 'roles'
    id           = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name         = db.Column(db.String(64), unique=True, nullable=False)
    display_name = db.Column(db.String(128), nullable=False)
    description  = db.Column(db.Text, nullable=True)
    is_system    = db.Column(db.Boolean, default=False, nullable=False)

    role_permissions = db.relationship('RolePermission', backref='role', cascade='all, delete-orphan', lazy='dynamic')
    user_roles       = db.relationship('UserRole', backref='role', cascade='all, delete-orphan', lazy='dynamic')

    def get_permissions(self):
        return [rp.permission for rp in self.role_permissions]

    def to_dict(self):
        return {
            'id':           self.id,
            'name':         self.name,
            'display_name': self.display_name,
            'description':  self.description or '',
            'is_system':    self.is_system,
            'permissions':  self.get_permissions(),
        }


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'
    role_id    = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
    permission = db.Column(db.String(64), primary_key=True, nullable=False)


class UserRole(db.Model):
    __tablename__ = 'user_roles'
    username = db.Column(db.String(64), db.ForeignKey('users.username', ondelete='CASCADE'), primary_key=True)
    role_id  = db.Column(db.Integer, db.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)


class AppConfig(db.Model):
    __tablename__ = 'app_config'
    id   = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Text, nullable=False, default='{}')


class User(db.Model):
    __tablename__ = 'users'
    username      = db.Column(db.String(64), primary_key=True)
    password_hash = db.Column(db.String(256), nullable=False)
    superadmin    = db.Column(db.Boolean, default=False, nullable=False)
    permissions   = db.Column(db.Text, default='[]', nullable=False)
    screens       = db.Column(db.Text, nullable=True)
    theme                = db.Column(db.String(32), default='violet', nullable=False)
    language             = db.Column(db.String(8), default='fr', nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False, server_default='false')

    def to_dict(self):
        return {
            'superadmin':  self.superadmin,
            'permissions': json.loads(self.permissions or '[]'),
            'screens':     json.loads(self.screens) if self.screens is not None else None,
            'theme':       self.theme,
            'language':    self.language,
        }

    @classmethod
    def from_dict(cls, username, entry):
        if isinstance(entry, str):
            return cls(username=username, password_hash=entry,
                       superadmin=False, permissions='[]')
        screens = entry.get('screens')
        return cls(
            username=username,
            password_hash=entry.get('password_hash') or LEGACY_PASSWORD_HASH_PLACEHOLDER,
            superadmin=bool(entry.get('superadmin', False)),
            permissions=json.dumps(entry.get('permissions', [])),
            screens=json.dumps(screens) if screens is not None else None,
            theme=entry.get('theme', 'violet'),
            language=entry.get('language', 'fr'),
        )


class ActivityLog(db.Model):
    __tablename__ = 'activity_log'
    id        = db.Column(db.Integer,    primary_key=True, autoincrement=True)
    timestamp = db.Column(db.String(32), nullable=False, index=True)
    username  = db.Column(db.String(64), nullable=False)
    action    = db.Column(db.String(32), nullable=False)
    filename  = db.Column(db.String(512), nullable=True)
    details   = db.Column(db.Text,       nullable=True)

    def to_dict(self):
        return {
            'id':        self.id,
            'timestamp': self.timestamp,
            'username':  self.username,
            'action':    self.action,
            'filename':  self.filename,
            'details':   self.details,
        }


class EncodeJob(db.Model):
    __tablename__ = 'encode_jobs'
    id        = db.Column(db.String(8),   primary_key=True)
    filename  = db.Column(db.String(512), nullable=False)
    status    = db.Column(db.String(16),  nullable=False, default='pending')
    added     = db.Column(db.String(32),  nullable=False)
    started   = db.Column(db.String(32),  nullable=True)
    finished  = db.Column(db.String(32),  nullable=True)
    new_name  = db.Column(db.String(512), nullable=True)
    before_mb = db.Column(db.Float,       nullable=True)
    after_mb  = db.Column(db.Float,       nullable=True)
    ratio     = db.Column(db.Float,       nullable=True)
    message   = db.Column(db.Text,        nullable=True)

    def to_dict(self):
        d = {
            'id':       self.id,
            'filename': self.filename,
            'status':   self.status,
            'added':    self.added,
            'started':  self.started,
            'finished': self.finished,
        }
        if self.new_name  is not None: d['new_name'] = self.new_name
        if self.before_mb is not None: d['before']   = self.before_mb
        if self.after_mb  is not None: d['after']    = self.after_mb
        if self.ratio     is not None: d['ratio']    = self.ratio
        if self.message   is not None: d['message']  = self.message
        return d


class SearchIndex(db.Model):
    __tablename__ = 'search_index'
    id          = db.Column(db.Integer,     primary_key=True, autoincrement=True)
    category    = db.Column(db.String(16),  nullable=False, index=True)
    lang        = db.Column(db.String(8),   nullable=False, index=True)
    title       = db.Column(db.String(256), nullable=False)
    url         = db.Column(db.String(512), nullable=False)
    description = db.Column(db.Text,        nullable=True)
    keywords    = db.Column(db.Text,        nullable=True)


class ClientHeartbeat(db.Model):
    __tablename__ = 'client_heartbeats'
    machine_id  = db.Column(db.String(128), primary_key=True)
    hostname    = db.Column(db.String(128), nullable=False, default='')
    client_name = db.Column(db.String(128), nullable=False, default='')
    screen_name = db.Column(db.String(128), nullable=False, default='')
    ip_address  = db.Column(db.String(64), nullable=False, default='')
    server_url  = db.Column(db.String(512), nullable=False, default='')
    client_version = db.Column(db.String(64), nullable=False, default='')
    uptime_seconds = db.Column(db.Integer, nullable=True)
    cpu_load_percent = db.Column(db.Float, nullable=True)
    ram_used_mb = db.Column(db.Integer, nullable=True)
    ram_total_mb = db.Column(db.Integer, nullable=True)
    temperature_c = db.Column(db.Float, nullable=True)
    disk_free_mb = db.Column(db.Integer, nullable=True)
    disk_total_mb = db.Column(db.Integer, nullable=True)
    resolution = db.Column(db.String(64), nullable=False, default='')
    last_error = db.Column(db.String(512), nullable=False, default='')
    last_seen   = db.Column(db.String(32), nullable=False, index=True)

    def to_dict(self):
        return {
            'machine_id': self.machine_id,
            'hostname': self.hostname,
            'client_name': self.client_name,
            'screen_name': self.screen_name,
            'ip_address': self.ip_address,
            'server_url': self.server_url,
            'client_version': self.client_version,
            'uptime_seconds': self.uptime_seconds,
            'cpu_load_percent': self.cpu_load_percent,
            'ram_used_mb': self.ram_used_mb,
            'ram_total_mb': self.ram_total_mb,
            'temperature_c': self.temperature_c,
            'disk_free_mb': self.disk_free_mb,
            'disk_total_mb': self.disk_total_mb,
            'resolution': self.resolution,
            'last_error': self.last_error,
            'last_seen': self.last_seen,
        }
