# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import copy

from flask import Blueprint, jsonify, redirect, request, session, url_for

from services.activity_svc import log_config_change
from services.config_svc import (
    load_config,
    save_config,
    normalize_default_screen_name,
    normalize_halo_color,
    DEFAULT_HALO_COLOR,
)
from services.campaign_svc import cleanup_campaigns_for_deleted_screen, get_campaigns, save_campaigns_to_config
from services.users_svc import has_screen_access
from services.media_svc import valid_screen_name
from services.i18n import _flash
from blueprints.guards import admin_guard, superadmin_guard, perm_guard, feature_guard

bp = Blueprint('screens', __name__)


def _settings_screens_url():
    return url_for('settings.admin_settings_section_page', section='gestion-ecrans')


def _redirect_after_screen_change(default_url):
    referrer = request.referrer or ''
    if '/admin/settings/gestion-ecrans' in referrer or '/admin/settings/administration' in referrer:
        return redirect(_settings_screens_url())
    return redirect(default_url)


@bp.route('/admin/screens/add', methods=['POST'])
def add_screen():
    redir = superadmin_guard()
    if redir: return redir
    redir = feature_guard('screens')
    if redir: return redir
    name = request.form.get('screen_name', '').strip().lower()
    if not valid_screen_name(name):
        _flash('flash_screen_name_invalid', 'error')
        return _redirect_after_screen_change(url_for('media.admin_media'))
    cfg     = load_config()
    screens = cfg.setdefault('screens', {})
    if name in screens:
        _flash('flash_screen_exists', 'error', name=name)
        return _redirect_after_screen_change(url_for('media.admin_media'))
    default_halo_color = normalize_halo_color(cfg.get('default_halo_color', DEFAULT_HALO_COLOR))
    screens[name] = {
        "order": [],
        "disabled": [],
        "disabled_groups": [],
        "durations": {},
        "schedules": {},
        "halo_color": default_halo_color,
    }
    save_config(cfg)
    log_config_change(session.get('user'), f'screen added:{name}')
    return _redirect_after_screen_change(url_for('media.admin_media') + f'?screen={name}')


@bp.route('/admin/screens/delete/<name>', methods=['POST'])
def delete_screen(name):
    redir = superadmin_guard()
    if redir: return redir
    redir = feature_guard('screens')
    if redir: return redir
    cfg     = load_config()
    screens = cfg.get('screens', {})
    if name in screens:
        del screens[name]
        save_campaigns_to_config(cfg, cleanup_campaigns_for_deleted_screen(get_campaigns(cfg), name))
        save_config(cfg)
        log_config_change(session.get('user'), f'screen deleted:{name}')
        _flash('flash_screen_deleted', 'success', name=name)
    return _redirect_after_screen_change(url_for('media.admin_media'))


@bp.route('/admin/screens/default-name', methods=['POST'])
def update_default_screen_name():
    redir = superadmin_guard()
    if redir: return redir
    redir = feature_guard('screens')
    if redir: return redir

    cfg = load_config()
    new_name = normalize_default_screen_name(request.form.get('default_screen_name', ''))
    cfg['default_screen_name'] = new_name
    save_config(cfg)
    if new_name:
        log_config_change(session.get('user'), f'default screen name:{new_name}')
    else:
        log_config_change(session.get('user'), 'default screen name reset')

    if new_name:
        _flash('flash_default_screen_name_updated', 'success', name=new_name)
    else:
        _flash('flash_default_screen_name_cleared', 'success')
    return redirect(_settings_screens_url())


@bp.route('/admin/screens/halo', methods=['POST'])
def update_screen_halo():
    redir = admin_guard()
    if redir: return redir
    redir = feature_guard('screens')
    if redir: return redir

    cfg = load_config()
    screen_name = request.form.get('screen_name', '').strip().lower()
    halo_color = normalize_halo_color(request.form.get('halo_color', ''))

    if screen_name:
        if screen_name not in cfg.get('screens', {}):
            _flash('flash_screen_not_found', 'error')
            return redirect(url_for('settings.admin_settings_section_page', section='application'))
        if not has_screen_access(screen_name):
            _flash('flash_no_perm', 'error')
            return redirect(url_for('settings.admin_settings_section_page', section='application'))
        cfg['screens'][screen_name]['halo_color'] = halo_color
        log_config_change(session.get('user'), f'screen halo {screen_name}:{halo_color}')
        _flash('flash_screen_halo_updated', 'success', name=screen_name, color=halo_color)
    else:
        cfg['default_halo_color'] = halo_color
        log_config_change(session.get('user'), f'default screen halo:{halo_color}')
        _flash('flash_default_screen_halo_updated', 'success', color=halo_color)

    save_config(cfg)
    return redirect(url_for('settings.admin_settings_section_page', section='application'))

@bp.route('/admin/screens/broadcast', methods=['POST'])
def broadcast_screen():
    redir = admin_guard()
    if redir: return redir
    redir = feature_guard('screens')
    if redir: return redir

    data   = request.get_json(silent=True) or {}
    source = data.get('source', '').strip().lower()
    targets = data.get('targets', [])

    if not isinstance(targets, list):
        return jsonify({'ok': False, 'error': 'invalid targets'})

    cfg     = load_config()
    screens = cfg.get('screens', {})

    if not has_screen_access(source):
        return jsonify({'ok': False, 'error': 'Access denied to source screen'})
    if source != '' and source not in screens:
        return jsonify({'ok': False, 'error': 'Source screen not found'})

    valid_targets = [
        str(t).strip().lower() for t in targets
        if str(t).strip().lower() in screens and has_screen_access(str(t).strip().lower())
    ]
    if not valid_targets:
        return jsonify({'ok': False, 'error': 'No valid target'})

    src = cfg if source == '' else screens[source]
    for t in valid_targets:
        for key in ('order', 'disabled', 'disabled_groups', 'durations', 'schedules'):
            screens[t][key] = copy.deepcopy(src.get(key, [] if key not in ('durations', 'schedules') else {}))

    cfg.setdefault('broadcast_links', {})[source] = valid_targets
    save_config(cfg)
    log_config_change(session.get('user'), f'screen broadcast {source} → {", ".join(valid_targets)}')
    return jsonify({'ok': True, 'targets': valid_targets})


@bp.route('/admin/screens/broadcast/stop', methods=['POST'])
def broadcast_stop():
    redir = admin_guard()
    if redir: return redir

    data   = request.get_json(silent=True) or {}
    source = data.get('source', '').strip().lower()

    if not has_screen_access(source):
        return jsonify({'ok': False, 'error': 'Access denied'})

    cfg = load_config()
    cfg.setdefault('broadcast_links', {}).pop(source, None)
    save_config(cfg)
    log_config_change(session.get('user'), f'broadcast stopped:{source}')
    return jsonify({'ok': True})


@bp.route('/screen_assign/<path:filename>', methods=['POST'])
def screen_assign(filename):
    import os
    g = perm_guard('toggle')
    if g: return g
    filename = os.path.basename(filename)
    data     = request.get_json(silent=True) or {}
    screen   = data.get('screen', '').strip().lower()
    action   = data.get('action', 'add')

    if not has_screen_access(screen):
        return jsonify({'ok': False, 'error': 'screen access denied'})
    if not valid_screen_name(screen):
        return jsonify({'ok': False, 'error': 'Invalid screen'})

    cfg = load_config()
    if screen not in cfg.get('screens', {}):
        return jsonify({'ok': False, 'error': 'Screen not found'})

    scfg  = cfg['screens'][screen]
    order = scfg.setdefault('order', [])

    if action == 'add' and filename not in order:
        order.append(filename)
    elif action == 'remove':
        if filename in order:
            order.remove(filename)
        disabled = scfg.get('disabled', [])
        if filename in disabled:
            disabled.remove(filename)

    save_config(cfg)
    verb = 'assigned' if action == 'add' else 'removed'
    log_config_change(session.get('user'), f'{filename} {verb} screen:{screen}', filename=filename)
    return jsonify({'ok': True})
