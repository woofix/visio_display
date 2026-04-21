from datetime import date

from flask import Blueprint, request, redirect, url_for, jsonify

from services.config_svc import load_config, save_config
from services.users_svc import is_admin, has_permission
from services.ephemeris_svc import generate_ephemeride_image
from services.i18n import _flash
from blueprints.guards import perm_guard, feature_guard_json

bp = Blueprint('ephemeris', __name__)


@bp.route('/regen_ephemeride', methods=['POST'])
def regen_ephemeride():
    g = perm_guard('ephemeris')
    if g: return g
    g = feature_guard_json('ephemeris')
    if g: return g
    generate_ephemeride_image(force=True)
    return jsonify({"ok": True})


@bp.route('/admin/events/add', methods=['POST'])
def add_event():
    if not is_admin(): return redirect(url_for('auth.login'))
    if not has_permission('ephemeris'):
        _flash('flash_no_perm', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=evenements')
    label    = request.form.get('label', '').strip()
    date_str = request.form.get('date', '').strip()
    if not label or not date_str:
        _flash('flash_label_date_required', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=evenements')
    try:
        date.fromisoformat(date_str)
    except ValueError:
        _flash('flash_invalid_date', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=evenements')
    cfg = load_config()
    cfg.setdefault("events", []).append({"label": label, "date": date_str})
    save_config(cfg)
    generate_ephemeride_image(force=True)
    _flash('flash_event_added', 'success', label=label)
    return redirect(url_for('settings.admin_settings_page') + '?tab=evenements')


@bp.route('/admin/events/delete/<int:idx>', methods=['POST'])
def delete_event(idx):
    if not is_admin(): return redirect(url_for('auth.login'))
    if not has_permission('ephemeris'):
        _flash('flash_no_perm', 'error')
        return redirect(url_for('settings.admin_settings_page') + '?tab=evenements')
    cfg    = load_config()
    events = cfg.get("events", [])
    if 0 <= idx < len(events):
        removed = events.pop(idx)
        cfg["events"] = events
        save_config(cfg)
        generate_ephemeride_image(force=True)
        _flash('flash_event_deleted', 'success', label=removed['label'])
    return redirect(url_for('settings.admin_settings_page') + '?tab=evenements')
