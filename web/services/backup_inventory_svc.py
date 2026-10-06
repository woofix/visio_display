"""Read SMB inventory in the background; never wait for SMB during a page request."""
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone

from services import backup_svc
from services.queue_svc import get_redis

CACHE_SECONDS = 300
LOCK_SECONDS = 45
SMB_TIMEOUT_SECONDS = 20


def list_smb_backups(settings):
    smb = backup_svc._parse_smb_url(settings.get('url', ''))
    username = str(settings.get('username', '') or smb['url_username']).strip()
    password = str(settings.get('password', '') or smb['url_password']).strip()
    with tempfile.TemporaryDirectory(prefix='visio-smb-inventory-') as tmp:
        command = backup_svc._build_smbclient_command(smb, username, password, tmp)
        command.extend(['-c', 'ls visio-backup-*.tar.gz'])
        result = subprocess.run(
            command, check=False, capture_output=True, text=True,
            timeout=SMB_TIMEOUT_SECONDS, env={**os.environ, 'LC_ALL': 'C'},
        )
    if result.returncode:
        if 'NT_STATUS_NO_SUCH_FILE listing' in (result.stdout or ''):
            return []
        raise RuntimeError('SMB inventory unavailable')
    items = {}
    for line in result.stdout.splitlines():
        match = re.match(r'^\s*(visio-backup-\d{8}-\d{6}\.tar\.gz)\s+([A-Z]+)\s+(\d+)\s+', line)
        if not match or 'D' in match[2]:
            continue
        filename = match[1]
        try:
            created = datetime.strptime(filename, 'visio-backup-%Y%m%d-%H%M%S.tar.gz').replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        items[filename] = {
            'filename': filename, 'size_bytes': int(match[3]),
            'created_at_iso': created.isoformat(),
        }
    return sorted(items.values(), key=lambda item: item['filename'], reverse=True)


def _cache_key(settings):
    # Credentials participate only in a digest, never in cache content or responses.
    digest = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    return 'visio-display:smb-inventory:' + digest


def _refresh_inventory(settings, key, token):
    try:
        items = list_smb_backups(settings)
        payload = {'status': 'ready', 'backups': items}
    except Exception:
        payload = {'status': 'error', 'backups': []}
    redis = get_redis()
    try:
        # An expired lease cannot overwrite a newer scan's result.
        redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "redis.call('set', KEYS[2], ARGV[2], 'EX', ARGV[3]); "
            "return redis.call('del', KEYS[1]) else return 0 end",
            2, key + ':lock', key, token, json.dumps(payload), CACHE_SECONDS,
        )
    except Exception:
        # Lease expiry lets a later request recover after Redis returns.
        pass


def get_smb_inventory(settings, *, refresh=False):
    if not settings.get('enabled') or not settings.get('url'):
        return {'status': 'disabled', 'backups': []}
    key = _cache_key(settings)
    redis = get_redis()
    try:
        raw = redis.get(key)
        cached = json.loads(raw) if raw else None
        if cached and cached['status'] == 'loading' and not redis.exists(key + ':lock'):
            cached = None
        if cached and (not refresh or cached['status'] == 'loading'):
            return cached
        token = str(uuid.uuid4())
        if redis.set(key + ':lock', token, nx=True, ex=LOCK_SECONDS):
            payload = {'status': 'loading', 'backups': []}
            redis.setex(key, CACHE_SECONDS, json.dumps(payload))
            try:
                threading.Thread(target=_refresh_inventory, args=(dict(settings), key, token), daemon=True).start()
            except Exception:
                redis.delete(key + ':lock')
                raise
            return payload
        return cached or {'status': 'loading', 'backups': []}
    except Exception:
        return {'status': 'error', 'backups': []}


def merge_backup_inventory(local, remote, remote_status):
    items = {}
    for item in remote:
        items[item['filename']] = {**item, 'local': False, 'smb': True}
    for item in local:
        filename = item['filename']
        on_smb = filename in items if remote_status == 'ready' else None
        items[filename] = {**item, 'local': True, 'smb': on_smb}
    return sorted(items.values(), key=lambda item: item['filename'], reverse=True)
