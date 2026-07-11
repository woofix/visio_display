# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from datetime import datetime, timedelta, UTC

from db import db, ClientHeartbeat


ONLINE_TTL = timedelta(minutes=5)
RETENTION_WINDOW = timedelta(days=30)


def _clean_text(value, max_len=128):
    return " ".join(str(value or "").split())[:max_len]


def _clean_resolution(value):
    return _clean_text(value, 64)


def _clean_error(value):
    return _clean_text(value, 512)


def _clean_int(value):
    if value in (None, ''):
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _clean_float(value):
    if value in (None, ''):
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


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


def _percent(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return round((numerator / denominator) * 100, 1)


def _format_mb(value):
    if value is None:
        return None
    if value >= 1024:
        return f'{value / 1024:.1f} GB'
    return f'{value} MB'


def _format_duration(seconds):
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _seconds = divmod(remainder, 60)
    if days:
        return f'{days}d {hours}h'
    if hours:
        return f'{hours}h {minutes}m'
    if minutes:
        return f'{minutes}m'
    return f'{_seconds}s'


def _health_status(item):
    ram_percent = _percent(item.get('ram_used_mb'), item.get('ram_total_mb'))
    disk_used_mb = None
    if item.get('disk_total_mb') is not None and item.get('disk_free_mb') is not None:
        disk_used_mb = max(0, item['disk_total_mb'] - item['disk_free_mb'])
    disk_percent = _percent(disk_used_mb, item.get('disk_total_mb'))
    cpu_percent = item.get('cpu_load_percent')
    temperature = item.get('temperature_c')
    last_error = bool((item.get('last_error') or '').strip())

    critical = (
        last_error
        or (cpu_percent is not None and cpu_percent >= 90)
        or (ram_percent is not None and ram_percent >= 95)
        or (disk_percent is not None and disk_percent >= 95)
        or (temperature is not None and temperature >= 80)
    )
    if critical:
        return 'critical'

    attention = (
        (cpu_percent is not None and cpu_percent >= 75)
        or (ram_percent is not None and ram_percent >= 85)
        or (disk_percent is not None and disk_percent >= 85)
        or (temperature is not None and temperature >= 70)
    )
    if attention:
        return 'attention'
    return 'healthy'


def _decorate_client(item):
    item['ram_percent'] = _percent(item.get('ram_used_mb'), item.get('ram_total_mb'))
    item['disk_used_mb'] = None
    if item.get('disk_total_mb') is not None and item.get('disk_free_mb') is not None:
        item['disk_used_mb'] = max(0, item['disk_total_mb'] - item['disk_free_mb'])
    item['disk_percent'] = _percent(item.get('disk_used_mb'), item.get('disk_total_mb'))
    item['uptime_human'] = _format_duration(item.get('uptime_seconds'))
    item['ram_used_human'] = _format_mb(item.get('ram_used_mb'))
    item['ram_total_human'] = _format_mb(item.get('ram_total_mb'))
    item['disk_free_human'] = _format_mb(item.get('disk_free_mb'))
    item['disk_total_human'] = _format_mb(item.get('disk_total_mb'))
    item['health_status'] = _health_status(item)
    return item


def prune_stale_clients():
    cutoff = datetime.now(UTC) - RETENTION_WINDOW
    for row in ClientHeartbeat.query.all():
        seen_at = _parse_iso(row.last_seen)
        if seen_at is None or seen_at < cutoff:
            db.session.delete(row)
    db.session.commit()


def record_client_heartbeat(machine_id, hostname='', client_name='', screen_name='',
                            ip_address='', server_url='', client_version='',
                            uptime_seconds=None, cpu_load_percent=None,
                            ram_used_mb=None, ram_total_mb=None,
                            temperature_c=None, disk_free_mb=None,
                            disk_total_mb=None, resolution='',
                            last_error=''):
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
    row.client_version = _clean_text(client_version, 64)
    row.uptime_seconds = _clean_int(uptime_seconds)
    row.cpu_load_percent = _clean_float(cpu_load_percent)
    row.ram_used_mb = _clean_int(ram_used_mb)
    row.ram_total_mb = _clean_int(ram_total_mb)
    row.temperature_c = _clean_float(temperature_c)
    row.disk_free_mb = _clean_int(disk_free_mb)
    row.disk_total_mb = _clean_int(disk_total_mb)
    row.resolution = _clean_resolution(resolution)
    row.last_error = _clean_error(last_error)
    row.last_seen = _now_iso()
    db.session.commit()
    return _decorate_client(row.to_dict())


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
        _decorate_client(item)
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
            'client_version',
            'uptime_seconds',
            'cpu_load_percent',
            'ram_used_mb',
            'ram_total_mb',
            'temperature_c',
            'disk_free_mb',
            'disk_total_mb',
            'resolution',
            'last_error',
        ):
            if not merged.get(field) and secondary.get(field):
                merged[field] = secondary[field]
        merged['display_name'] = _display_name(merged)
        merged['is_online'] = bool(
            preferred.get('is_online') or secondary.get('is_online')
        )
        merged['last_seen_relative'] = _relative_last_seen(merged.get('last_seen'))
        _decorate_client(merged)
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
        _decorate_client(item)
        visible_clients.append(item)

    return sorted(
        visible_clients,
        key=lambda item: (
            0 if item.get('is_online') else 1,
            (item.get('display_name') or '').casefold(),
            (item.get('hostname') or '').casefold(),
        ),
    )
