# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os


def _clamp_percent(value):
    if value is None:
        return None
    return round(min(max(float(value), 0.0), 100.0), 1)


def _read_cpu_percent():
    try:
        load1, _load5, _load15 = os.getloadavg()
    except (AttributeError, OSError):
        return None

    cpu_count = os.cpu_count() or 1
    return _clamp_percent((load1 / cpu_count) * 100)


def _read_memory_stats():
    try:
        with open('/proc/meminfo', encoding='utf-8') as handle:
            lines = handle.readlines()
    except OSError:
        return {
            'percent': None,
            'used_gb': None,
            'total_gb': None,
        }

    values = {}
    for line in lines:
        if ':' not in line:
            continue
        key, raw_value = line.split(':', 1)
        parts = raw_value.strip().split()
        if not parts:
            continue
        try:
            values[key] = int(parts[0])
        except ValueError:
            continue

    total_kb = values.get('MemTotal')
    available_kb = values.get('MemAvailable')
    if total_kb in (None, 0) or available_kb is None:
        return {
            'percent': None,
            'used_gb': None,
            'total_gb': round(total_kb / (1024 * 1024), 1) if total_kb else None,
        }

    used_kb = max(0, total_kb - available_kb)
    return {
        'percent': _clamp_percent((used_kb / total_kb) * 100),
        'used_gb': round(used_kb / (1024 * 1024), 1),
        'total_gb': round(total_kb / (1024 * 1024), 1),
    }


def get_server_stats():
    memory = _read_memory_stats()
    return {
        'cpu_percent': _read_cpu_percent(),
        'memory_percent': memory['percent'],
        'memory_used_gb': memory['used_gb'],
        'memory_total_gb': memory['total_gb'],
    }
