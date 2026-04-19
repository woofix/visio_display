from flask import Blueprint, request, redirect, url_for, flash, jsonify

from services.config_svc import load_config, save_config
from services.users_svc import has_screen_access
from services.media_svc import valid_screen_name
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
        flash("Nom d'écran invalide (lettres minuscules, chiffres, tirets, underscores, 1-32 chars).", 'error')
        return redirect(url_for('media.admin_media'))
    cfg     = load_config()
    screens = cfg.setdefault('screens', {})
    if name in screens:
        flash(f"L'écran « {name} » existe déjà.", 'error')
        return redirect(url_for('media.admin_media'))
    screens[name] = {"order": [], "disabled": [], "disabled_groups": [], "durations": {}, "schedules": {}}
    save_config(cfg)
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
        save_config(cfg)
        flash(f"Écran « {name} » supprimé.", 'success')
    return redirect(url_for('media.admin_media'))


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
    return jsonify({'ok': True})
