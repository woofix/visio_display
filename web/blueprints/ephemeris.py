# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from datetime import date

from flask import Blueprint, jsonify, redirect, request, session

from services.activity_svc import log_config_change
from services.config_svc import load_config, save_config
from services.ephemeris_svc import ensure_ephemeride_image_async
from services.i18n import _flash
from blueprints.guards import feature_guard_json, superadmin_guard, superadmin_guard_json

bp = Blueprint('ephemeris', __name__)


@bp.route('/regen_ephemeride', methods=['POST'])
def regen_ephemeride():
    g = superadmin_guard_json()
    if g: return g
    g = feature_guard_json('ephemeris')
    if g: return g
    ensure_ephemeride_image_async(force=True)
    log_config_change(session.get('user'), 'ephemeris regenerated')
    if 'application/json' not in request.headers.get('Accept', ''):
        _flash('flash_ephemeris_regenerated', 'success')
        return redirect('/admin/settings/meteo')
    return jsonify({"ok": True})


@bp.route('/admin/events/add', methods=['POST'])
def add_event():
    redir = superadmin_guard()
    if redir:
        return redir
    label    = request.form.get('label', '').strip()
    date_str = request.form.get('date', '').strip()
    if not label or not date_str:
        _flash('flash_label_date_required', 'error')
        return redirect('/admin/settings/meteo')
    try:
        date.fromisoformat(date_str)
    except ValueError:
        _flash('flash_invalid_date', 'error')
        return redirect('/admin/settings/meteo')
    cfg = load_config()
    cfg.setdefault("events", []).append({"label": label, "date": date_str})
    save_config(cfg)
    log_config_change(session.get('user'), f'event added:{label} ({date_str})')
    ensure_ephemeride_image_async(force=True)
    _flash('flash_event_added', 'success', label=label)
    return redirect('/admin/settings/meteo')


@bp.route('/admin/events/delete/<int:idx>', methods=['POST'])
def delete_event(idx):
    redir = superadmin_guard()
    if redir:
        return redir
    cfg    = load_config()
    events = cfg.get("events", [])
    if 0 <= idx < len(events):
        removed = events.pop(idx)
        cfg["events"] = events
        save_config(cfg)
        log_config_change(session.get('user'), f'event deleted:{removed["label"]} ({removed["date"]})')
        ensure_ephemeride_image_async(force=True)
        _flash('flash_event_deleted', 'success', label=removed['label'])
    return redirect('/admin/settings/meteo')
