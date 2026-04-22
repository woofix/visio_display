# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

from flask import Blueprint, jsonify, redirect, request, session, url_for

from services.activity_svc import log_config_change
from services.config_svc import load_config, save_config, normalize_default_screen_name
from services.campaign_svc import cleanup_campaigns_for_deleted_screen, get_campaigns, save_campaigns_to_config
from services.users_svc import has_screen_access
from services.media_svc import valid_screen_name
from services.i18n import _flash
from blueprints.guards import superadmin_guard, perm_guard, feature_guard

bp = Blueprint('screens', __name__)


@bp.route('/admin/screens/add', methods=['POST'])
def add_screen():
    redir = superadmin_guard()
    if redir: return redir
    redir = feature_guard('screens')
    if redir: return redir
    name = request.form.get('screen_name', '').strip().lower()
    if not valid_screen_name(name):
        _flash('flash_screen_name_invalid', 'error')
        return redirect(url_for('media.admin_media'))
    cfg     = load_config()
    screens = cfg.setdefault('screens', {})
    if name in screens:
        _flash('flash_screen_exists', 'error', name=name)
        return redirect(url_for('media.admin_media'))
    screens[name] = {"order": [], "disabled": [], "disabled_groups": [], "durations": {}, "schedules": {}}
    save_config(cfg)
    log_config_change(session.get('user'), f'écran ajouté:{name}')
    return redirect(url_for('media.admin_media') + f'?screen={name}')


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
        log_config_change(session.get('user'), f'écran supprimé:{name}')
        _flash('flash_screen_deleted', 'success', name=name)
    return redirect(url_for('media.admin_media'))


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
        log_config_change(session.get('user'), f'nom écran par défaut:{new_name}')
    else:
        log_config_change(session.get('user'), 'nom écran par défaut réinitialisé')

    if new_name:
        _flash('flash_default_screen_name_updated', 'success', name=new_name)
    else:
        _flash('flash_default_screen_name_cleared', 'success')
    return redirect(url_for('users.admin_superadmin_page'))


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
        return jsonify({'ok': False, 'error': 'Écran invalide'})

    cfg = load_config()
    if screen not in cfg.get('screens', {}):
        return jsonify({'ok': False, 'error': 'Écran introuvable'})

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
    verb = 'affecté' if action == 'add' else 'retiré'
    log_config_change(session.get('user'), f'{filename} {verb} écran:{screen}', filename=filename)
    return jsonify({'ok': True})
