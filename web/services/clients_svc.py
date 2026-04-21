from datetime import datetime, timedelta, UTC

from db import db, ClientHeartbeat


ONLINE_TTL = timedelta(minutes=5)
RETENTION_WINDOW = timedelta(days=30)


def _clean_text(value, max_len=128):
    return " ".join(str(value or "").split())[:max_len]


def _now_iso():
    return datetime.now(UTC).isoformat(timespec='seconds')


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _display_name(entry):
    return (
        entry.get('client_name')
        or entry.get('screen_name')
        or entry.get('hostname')
        or entry.get('ip_address')
        or entry.get('machine_id')
        or 'Client'
    )


def _logical_client_key(entry):
    machine_id = (entry.get('machine_id') or '').strip().casefold()
    if machine_id:
        return ('machine', machine_id)

    client_name = (entry.get('client_name') or '').strip().casefold()
    hostname = (entry.get('hostname') or '').strip().casefold()
    if client_name and hostname:
        return ('client-host', client_name, hostname)
    if client_name:
        return ('client', client_name)
    if hostname:
        return ('host', hostname)
    screen_name = (entry.get('screen_name') or '').strip().casefold()
    if screen_name:
        return ('screen', screen_name)
    return ('machine', '')


def _relative_last_seen(last_seen):
    dt = _parse_iso(last_seen)
    if dt is None:
        return 'unknown'
    now = datetime.now(UTC)
    delta = now - dt
    if delta < timedelta(seconds=60):
        return 'just now'
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f'{minutes} min ago'
    hours = minutes // 60
    if hours < 24:
        return f'{hours} h ago'
    days = hours // 24
    return f'{days} d ago'


def prune_stale_clients():
    cutoff = datetime.now(UTC) - RETENTION_WINDOW
    for row in ClientHeartbeat.query.all():
        seen_at = _parse_iso(row.last_seen)
        if seen_at is None or seen_at < cutoff:
            db.session.delete(row)
    db.session.commit()


def record_client_heartbeat(machine_id, hostname='', client_name='', screen_name='',
                            ip_address='', server_url=''):
    machine_id = _clean_text(machine_id, 128)
    if not machine_id:
        return None

    row = db.session.get(ClientHeartbeat, machine_id)
    if row is None:
        row = ClientHeartbeat(machine_id=machine_id)
        db.session.add(row)

    row.hostname = _clean_text(hostname, 128)
    row.client_name = _clean_text(client_name, 128)
    row.screen_name = _clean_text(screen_name, 128)
    row.ip_address = _clean_text(ip_address, 64)
    row.server_url = _clean_text(server_url, 512)
    row.last_seen = _now_iso()
    db.session.commit()
    return row.to_dict()


def list_known_clients():
    prune_stale_clients()
    now = datetime.now(UTC)
    clients_by_key = {}
    for row in ClientHeartbeat.query.all():
        item = row.to_dict()
        seen_at = _parse_iso(item.get('last_seen'))
        item['is_online'] = bool(seen_at and now - seen_at <= ONLINE_TTL)
        item['display_name'] = _display_name(item)
        item['last_seen_relative'] = _relative_last_seen(item.get('last_seen'))
        key = _logical_client_key(item)
        current = clients_by_key.get(key)
        if current is None:
            clients_by_key[key] = item
            continue

        current_seen = _parse_iso(current.get('last_seen'))
        incoming_is_newer = bool(
            seen_at and (current_seen is None or seen_at >= current_seen)
        )
        preferred = item if incoming_is_newer else current
        secondary = current if incoming_is_newer else item

        merged = dict(preferred)
        for field in (
            'hostname',
            'client_name',
            'screen_name',
            'ip_address',
            'server_url',
            'machine_id',
        ):
            if not merged.get(field) and secondary.get(field):
                merged[field] = secondary[field]
        merged['display_name'] = _display_name(merged)
        merged['is_online'] = bool(
            preferred.get('is_online') or secondary.get('is_online')
        )
        merged['last_seen_relative'] = _relative_last_seen(merged.get('last_seen'))
        clients_by_key[key] = merged

    visible_clients = []
    for item in clients_by_key.values():
        if not item.get('is_online'):
            continue
        seen_at = _parse_iso(item.get('last_seen'))
        if seen_at is None:
            continue
        item['seconds_until_hidden'] = max(
            0,
            int((ONLINE_TTL - (now - seen_at)).total_seconds()),
        )
        visible_clients.append(item)

    return sorted(
        visible_clients,
        key=lambda item: (
            0 if item.get('is_online') else 1,
            (item.get('display_name') or '').casefold(),
            (item.get('hostname') or '').casefold(),
        ),
    )
