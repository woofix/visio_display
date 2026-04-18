import json
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


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
    theme         = db.Column(db.String(32), default='violet', nullable=False)
    language      = db.Column(db.String(8), default='fr', nullable=False)

    def to_dict(self):
        return {
            'password':    self.password_hash,
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
            password_hash=entry.get('password', ''),
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
