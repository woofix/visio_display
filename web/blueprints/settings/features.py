# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

from flask import redirect, request, session

from blueprints.guards import superadmin_guard
from constants import ALL_FEATURES
from services.activity_svc import log_config_change
from services.config_svc import load_config, save_config
from services.i18n import _flash
from services.settings_sections import settings_section_url

from . import bp


@bp.route('/admin/features')
def admin_features_page():
    g = superadmin_guard()
    if g: return g
    return redirect(settings_section_url('features'))


@bp.route('/admin/features/toggle', methods=['POST'])
def toggle_feature():
    g = superadmin_guard()
    if g: return g
    feature = request.form.get('feature', '').strip()
    valid_keys = {k for k, _, _ in ALL_FEATURES}
    if feature not in valid_keys:
        _flash('flash_feature_disabled_access', 'error')
        _flash('flash_feature_disabled_access', 'error')
        return redirect(settings_section_url('features'))
    cfg = load_config()
    features = dict(cfg.get('features', {}))
    features[feature] = not bool(features.get(feature, True))
    cfg['features'] = features
    save_config(cfg)
    log_config_change(session.get('user'), f'feature {feature}: {features[feature]}')
    _flash('flash_feature_updated', 'success')
    return redirect(settings_section_url('features'))
