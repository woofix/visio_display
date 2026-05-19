# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import copy
import os
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

from constants import UPLOAD_FOLDER
from services.config_svc import (
    load_config,
    save_config,
    get_default_screen_name,
    get_default_screen_key,
    get_screen_keys,
    get_screen_config,
    normalize_screen_key,
)
from services.users_svc import load_users, has_permission, has_screen_access, is_superadmin
from services.media_svc import (
    get_all_media, get_logo_path,
    clean_filename, get_media_groups,
    collect_group_states, is_media_disabled, normalize_group_name,
    cleanup_orphan_group_metadata,
    delete_image_variants, delete_media_thumbnail, delete_video_variants,
    build_media_metadata_map,
    build_media_preview_map,
)
from services.media_cleanup_svc import analyze_media_cleanup
from services.playlist_cache_svc import bump_media_revision
from services.queue_svc import load_queue, save_queue
from services.upload_svc import handle_media_upload
from services.i18n import _flash, _t
from services.activity_svc import log_activity
from services.schedule_svc import (
    build_schedule_entries, schedule_summary, analyze_schedule_week,
    parse_iso_date, start_of_week, week_days,
)
from services.campaign_svc import get_campaigns, save_campaigns_to_config, cleanup_campaigns_for_deleted_media
from blueprints.guards import (
    admin_guard,
    perm_guard,
    feature_guard,
    feature_guard_json,
    permission_redirect_guard,
)

bp = Blueprint('media', __name__)

def _propagate_broadcast(source, cfg):
    source = normalize_screen_key(source, cfg)
    targets = cfg.get('broadcast_links', {}).get(source, [])
    if not targets:
        return
    screens = cfg.get('screens', {})
    src = cfg if source == '' else screens.get(source, {})
    for t in targets:
        if t == '' or t in screens:
            target_cfg = cfg if t == '' else screens[t]
            for key in ('order', 'disabled', 'disabled_groups', 'durations', 'schedules'):
                default = {} if key in ('durations', 'schedules') else []
                target_cfg[key] = copy.deepcopy(src.get(key, default))


def _get_schedule_bucket(cfg, screen):
    screen = normalize_screen_key(screen, cfg)
    if screen:
        if screen not in cfg.get('screens', {}):
            return None
        return cfg['screens'][screen].setdefault('schedules', {})
    return cfg.setdefault('schedules', {})


def _scope_details(screen):
    return f'screen:{screen}' if screen else 'global'


def _is_generated_menu_video(cfg, filename):
    generated = cfg.get("generated_menus", {})
    return (
        isinstance(generated, dict)
        and filename in generated
        and str(filename or "").lower().endswith(".mp4")
    )


def _assigned_media_for_screen(all_media, screen_cfg):
    assigned_set = set(screen_cfg.get('order', []))
    all_media_set = set(all_media)
    files = [f for f in screen_cfg.get('order', []) if f in all_media_set]
    unassigned = [f for f in all_media if f not in assigned_set]
    return files, unassigned


def _schedule_details(sched):
    parts = []
    for key in ('time_start', 'time_end', 'date_start', 'date_end'):
        value = sched.get(key)
        if value:
            parts.append(f'{key}={value}')
    return ', '.join(parts) if parts else 'no rule'


def _build_schedule_payload(data):
    sched = {}
    for key in ('time_start', 'time_end', 'date_start', 'date_end'):
        value = str(data.get(key, '')).strip()
        if value:
            sched[key] = value

    for time_key in ('time_start', 'time_end'):
        if time_key in sched:
            try:
                hour, minute = map(int, sched[time_key].split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except (TypeError, ValueError):
                return None

    for date_key in ('date_start', 'date_end'):
        if date_key in sched:
            try:
                from datetime import date
                date.fromisoformat(sched[date_key])
            except (TypeError, ValueError):
                return None

    return sched


@bp.route('/admin/media')
def admin_media():
    redir = admin_guard()
    if redir: return redir
    cfg       = load_config()
    screen    = normalize_screen_key(request.args.get('screen', ''), cfg)
    all_media = get_all_media()
    media_metadata = build_media_metadata_map(all_media, preview_contexts=('admin', 'preview'), generate_missing=True)
    infos     = media_metadata
    q         = load_queue()
    queued    = {j['filename'] for j in q if j['status'] in ('pending', 'processing')}
    users     = load_users()
    screens   = [s for s in get_screen_keys(cfg) if s in cfg.get('screens', {}) and has_screen_access(s)]
    default_screen_key = get_default_screen_key(cfg)
    default_screen_label = get_default_screen_name(cfg) or _t('media_screen_default')
    screen_labels = {
        screen_name: (default_screen_label if screen_name == default_screen_key else screen_name)
        for screen_name in screens
    }

    if screen and screen in cfg.get('screens', {}):
        if not has_screen_access(screen):
            return redirect('/admin/media?screen=' + (screens[0] if screens else ''))
        scfg         = cfg['screens'][screen]
        files, unassigned = _assigned_media_for_screen(all_media, scfg)
        view_cfg     = {'disabled': scfg.get('disabled', []),
                        'disabled_groups': scfg.get('disabled_groups', []),
                        'durations': scfg.get('durations', {})}
        schedules    = scfg.get('schedules', {})
    else:
        if not has_screen_access(''):
            return redirect('/admin/media?screen=' + (screens[0] if screens else ''))
        screen     = ''
        files, unassigned = _assigned_media_for_screen(all_media, cfg)
        view_cfg   = cfg
        schedules  = cfg.get('schedules', {})

    media_groups = {f: get_media_groups(f, cfg) for f in all_media}
    preview_urls = {
        filename: media_metadata[filename].get('preview_urls', {}).get('admin') or '/static/images/logo.svg'
        for filename in all_media
    }
    preview_media_urls = {
        filename: (
            media_metadata[filename].get('preview_urls', {}).get('preview')
            or media_metadata[filename].get('preview_urls', {}).get('original')
        )
        for filename in all_media
    }
    effective_cfg = dict(view_cfg)
    effective_cfg['groups'] = cfg.get('groups', {})
    effective_cfg['group_pools'] = cfg.get('group_pools', {})
    effective_cfg['group_screens'] = cfg.get('group_screens', {})
    group_states = collect_group_states(files, effective_cfg, screen=screen)
    disabled_map = {f: is_media_disabled(f, effective_cfg) for f in files}

    broadcast_links = cfg.get('broadcast_links', {})
    active_broadcast_targets = broadcast_links.get(screen, [])
    broadcast_source = next((src for src, tgts in broadcast_links.items() if screen in tgts), None)

    return render_template('admin_media.html',
        files=files, unassigned=unassigned, infos=infos, cfg=view_cfg, queued=queued,
        schedules=schedules, current_screen=screen, screens=screens,
        screen_labels=screen_labels,
        default_screen_key=default_screen_key,
        has_default_screen=False,
        media_groups=media_groups, group_states=group_states, disabled_map=disabled_map,
        preview_urls=preview_urls, preview_media_urls=preview_media_urls,
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path(), can_toggle=has_permission('toggle'),
        can_schedule=has_permission('schedule'),
        current_user_is_superadmin=is_superadmin(),
        current_screen_label=screen_labels.get(screen, screen),
        active_broadcast_targets=active_broadcast_targets,
        broadcast_source=broadcast_source)


@bp.route('/admin/media/cleanup')
def admin_media_cleanup_legacy():
    redir = admin_guard()
    if redir:
        return redir
    return redirect(url_for('media.admin_media_cleanup_page'))


@bp.route('/admin/settings/nettoyage-medias')
def admin_media_cleanup_page():
    redir = admin_guard()
    if redir:
        return redir
    if not has_permission('cleanup'):
        _flash('flash_no_perm', 'error')
        return redirect(url_for('admin.admin_page'))
    cfg = load_config()
    users = load_users()
    cleanup = analyze_media_cleanup(cfg)
    cleanup_files = set()
    for key, items in cleanup.get("categories", {}).items():
        if key == "duplicates":
            for group in items:
                cleanup_files.update(file_item["filename"] for file_item in group.get("files", []))
            continue
        cleanup_files.update(item["filename"] for item in items)
    preview_urls = build_media_preview_map(sorted(cleanup_files, key=str.casefold), context='admin', generate_missing=True)
    return render_template(
        'admin_media_cleanup.html',
        cleanup=cleanup,
        preview_urls=preview_urls,
        users=list(users.keys()),
        current_user=session.get('user'),
        logo_path=get_logo_path(),
        can_delete=has_permission('delete'),
        current_user_is_superadmin=is_superadmin(),
    )


@bp.route('/admin/programming')
def admin_programming_page():
    redir = admin_guard()
    if redir:
        return redir
    g = feature_guard('schedule')
    if g:
        return g

    cfg = load_config()
    users = load_users()
    files = get_all_media()
    media_infos = build_media_metadata_map(files, preview_contexts=('campaign',), generate_missing=True)
    allowed_screens = [screen for screen in cfg.get('screens', {}) if has_screen_access(screen)]
    default_screen_name = get_default_screen_name(cfg) or _t('media_screen_default')

    requested_week = parse_iso_date(request.args.get('week', '').strip())
    week_start = start_of_week(requested_week or datetime.now().date())
    week_end = week_start + timedelta(days=6)

    entries = build_schedule_entries(cfg, media_infos, allowed_screens, default_screen_name)
    analysis = analyze_schedule_week(entries, week_start)
    entry_issue_counts = analysis.get('entry_issue_counts', {})
    calendar_rows = analysis.get('calendar_rows', [])

    for entry in entries:
        issues = entry_issue_counts.get(entry['id'], {})
        entry['summary'] = schedule_summary(entry, _t)
        entry['overlap_count'] = issues.get('overlaps', 0)
        entry['gap_count'] = issues.get('gaps', 0)

    for row in calendar_rows:
        row['item_count'] = sum(len(cell.get('items', [])) for cell in row.get('cells', []))

    week_labels = []
    for day in week_days(week_start):
        weekday_label = _t(f'weekday_short_{day.weekday()}')
        week_labels.append({
            'date': day.isoformat(),
            'label': f'{weekday_label} {day.strftime("%d/%m")}',
        })

    screen_choices = ([('', default_screen_name)] if has_screen_access('') else []) + [(screen, screen) for screen in allowed_screens]
    filter_screen_choices = ([('__global__', default_screen_name)] if has_screen_access('') else []) + [(screen, screen) for screen in allowed_screens]
    group_choices = sorted({group for entry in entries for group in entry.get('groups', [])}, key=str.casefold)

    return render_template(
        'admin_programming.html',
        entries=entries,
        calendar_rows=calendar_rows,
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        previous_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        week_labels=week_labels,
        screen_choices=screen_choices,
        filter_screen_choices=filter_screen_choices,
        group_choices=group_choices,
        media_choices=files,
        media_items=[
            {
                'filename': f,
                'type': media_infos[f].get('type', 'unknown'),
                'size': media_infos[f].get('size', '--'),
                'dims': media_infos[f].get('dims', '--'),
                'preview_url': media_infos[f].get('preview_urls', {}).get('campaign'),
            }
            for f in files
        ],
        users=list(users.keys()),
        current_user=session.get('user'),
        logo_path=get_logo_path(),
        can_schedule=has_permission('schedule'),
        current_user_is_superadmin=is_superadmin(),
    )


@bp.route('/admin/upload')
def admin_upload_page():
    redir = admin_guard()
    if redir: return redir
    redir = feature_guard('upload')
    if redir: return redir
    redir = permission_redirect_guard('upload', 'admin.admin_page')
    if redir: return redir
    users = load_users()
    return render_template('admin_upload.html',
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path(),
        current_user_is_superadmin=is_superadmin())


@bp.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    redir = admin_guard()
    if redir: return redir
    g = feature_guard_json('delete')
    if g: return g
    if not has_permission('delete'):
        _flash('flash_no_perm_delete', 'error')
        return redirect(url_for('media.admin_media'))
    filename = os.path.basename(filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)
        delete_media_thumbnail(filename)
        delete_image_variants(filename)
        delete_video_variants(filename)
        log_activity(session.get('user'), 'delete', filename=filename)
        cfg = load_config()
        cfg["order"]    = [f for f in cfg.get("order", [])    if f != filename]
        cfg["disabled"] = [f for f in cfg.get("disabled", []) if f != filename]
        cfg["durations"].pop(filename, None)
        cfg.get("groups", {}).pop(filename, None)
        cfg.get("schedules", {}).pop(filename, None)
        cfg.get("generated_menus", {}).pop(filename, None)
        cleanup_orphan_group_metadata(cfg)
        save_campaigns_to_config(cfg, cleanup_campaigns_for_deleted_media(get_campaigns(cfg), filename))
        for scfg in cfg.get('screens', {}).values():
            scfg['order']    = [f for f in scfg.get('order', [])    if f != filename]
            scfg['disabled'] = [f for f in scfg.get('disabled', []) if f != filename]
            scfg.get('durations', {}).pop(filename, None)
            scfg.get('schedules', {}).pop(filename, None)
        save_config(cfg)
        bump_media_revision()
        q = load_queue()
        q = [j for j in q if not (j['filename'] == filename and j['status'] == 'pending')]
        save_queue(q)
        _flash('flash_deleted', 'success', filename=filename)
    else:
        _flash('flash_not_found', 'error', filename=filename)
    return redirect(url_for('media.admin_media'))


@bp.route('/upload', methods=['POST'])
def upload_file():
    redir = admin_guard()
    if redir: return redir
    g = feature_guard_json('upload')
    if g: return g
    if not has_permission('upload'):
        _flash('flash_no_perm_upload', 'error')
        return redirect(url_for('media.admin_upload_page'))
    return handle_media_upload(request.files.getlist('file'), request.form, session.get('user'))


@bp.route('/toggle/<filename>', methods=['POST'])
def toggle_file(filename):
    g = perm_guard('toggle')
    if g: return g
    filename = os.path.basename(filename)
    data     = request.get_json(silent=True) or {}
    cfg = load_config()
    screen   = normalize_screen_key(data.get('screen', ''), cfg)
    if filename not in set(get_all_media()):
        return jsonify({"error": "media not found"}), 404
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403

    screen_cfg = get_screen_config(cfg, screen)
    if screen_cfg is None:
        return jsonify({"error": "screen not found"}), 404
    disabled = screen_cfg.setdefault('disabled', [])

    if filename in disabled:
        disabled.remove(filename)
        state = "enabled"
    else:
        disabled.append(filename)
        state = "disabled"

    _propagate_broadcast(screen, cfg)
    save_config(cfg)
    details = state + (' → ' + screen if screen else '')
    log_activity(session.get('user'), 'toggle', filename=filename, details=details)
    effective_cfg = dict(screen_cfg)
    effective_cfg['groups'] = cfg.get('groups', {})
    effective_disabled = is_media_disabled(filename, effective_cfg)
    return jsonify({
        "file": filename,
        "state": state,
        "manual_disabled": filename in disabled,
        "group_disabled": effective_disabled and filename not in disabled,
        "disabled": effective_disabled,
    })


@bp.route('/set_groups/<filename>', methods=['POST'])
def set_groups(filename):
    g = perm_guard('toggle')
    if g: return g
    g = feature_guard_json('groups')
    if g: return g
    filename = os.path.basename(filename)
    data = request.get_json(silent=True) or {}
    raw_groups = data.get('groups', [])

    if isinstance(raw_groups, str):
        raw_groups = raw_groups.split(',')
    if not isinstance(raw_groups, list):
        return jsonify({"error": "invalid groups"}), 400

    groups = []
    seen = set()
    for group in raw_groups:
        name = normalize_group_name(group)
        key = name.casefold()
        if name and key not in seen:
            groups.append(name)
            seen.add(key)

    cfg = load_config()
    groups_map = cfg.setdefault('groups', {})
    if groups:
        groups_map[filename] = groups
    elif filename in groups_map:
        del groups_map[filename]
    cleanup_orphan_group_metadata(cfg)

    save_config(cfg)
    details = f'groups={", ".join(groups)}' if groups else 'groups removed'
    log_activity(session.get('user'), 'config', filename=filename, details=details)
    return jsonify({"ok": True, "groups": groups})


@bp.route('/set_group_screens/<path:group_name>', methods=['POST'])
def set_group_screens(group_name):
    g = perm_guard('toggle')
    if g: return g
    normalized = normalize_group_name(group_name)
    if not normalized:
        return jsonify({"error": "invalid group"}), 400
    data = request.get_json(silent=True) or {}
    screens_list = data.get('screens', [])
    if not isinstance(screens_list, list):
        return jsonify({"error": "invalid screens"}), 400
    cfg = load_config()
    valid_screens = {normalize_screen_key(screen, cfg) for screen in cfg.get('screens', {}).keys()} | {''}
    normalized_screens = []
    seen = set()
    for screen in screens_list:
        normalized_screen = normalize_screen_key(screen, cfg)
        if normalized_screen not in valid_screens:
            return jsonify({"error": "screen not found"}), 404
        if not has_screen_access(normalized_screen):
            return jsonify({"error": "screen access denied"}), 403
        if normalized_screen not in seen:
            normalized_screens.append(normalized_screen)
            seen.add(normalized_screen)
    screens_list = normalized_screens
    group_screens = cfg.setdefault('group_screens', {})
    if screens_list:
        group_screens[normalized] = screens_list
    else:
        group_screens.pop(normalized, None)
    save_config(cfg)
    details = f'group assignment {normalized}: {", ".join(screens_list) if screens_list else "all screens"}'
    log_activity(session.get('user'), 'config', details=details)
    return jsonify({"ok": True, "group": normalized, "screens": screens_list})


@bp.route('/set_group_pool/<path:group_name>', methods=['POST'])
def set_group_pool(group_name):
    g = perm_guard('toggle')
    if g: return g
    normalized = normalize_group_name(group_name)
    if not normalized:
        return jsonify({"error": "invalid group"}), 400
    data = request.get_json(silent=True) or {}
    try:
        pool_size = max(0, int(data.get('pool_size', 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid pool_size"}), 400
    cfg = load_config()
    group_pools = cfg.setdefault('group_pools', {})
    if pool_size > 0:
        group_pools[normalized] = pool_size
    else:
        group_pools.pop(normalized, None)
    save_config(cfg)
    details = f'group pool {normalized}: {pool_size}' if pool_size > 0 else f'group pool {normalized} removed'
    log_activity(session.get('user'), 'config', details=details)
    return jsonify({"ok": True, "group": normalized, "pool_size": pool_size})


@bp.route('/toggle_group/<path:group_name>', methods=['POST'])
def toggle_group(group_name):
    g = perm_guard('toggle')
    if g: return g
    g = feature_guard_json('groups')
    if g: return g
    data = request.get_json(silent=True) or {}
    cfg = load_config()
    screen = normalize_screen_key(data.get('screen', ''), cfg)
    normalized_group = normalize_group_name(group_name)
    if not normalized_group:
        return jsonify({"error": "invalid group"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403

    screen_cfg = get_screen_config(cfg, screen)
    if screen_cfg is None:
        return jsonify({"error": "screen not found"}), 404
    disabled_groups = screen_cfg.setdefault('disabled_groups', [])

    if normalized_group in disabled_groups:
        disabled_groups.remove(normalized_group)
        state = "enabled"
    else:
        disabled_groups.append(normalized_group)
        state = "disabled"

    _propagate_broadcast(screen, cfg)
    save_config(cfg)
    details = state + ' (groupe: ' + normalized_group + ')' + (' → ' + screen if screen else '')
    log_activity(session.get('user'), 'toggle', filename=None, details=details)
    return jsonify({"state": state, "group": normalized_group})


@bp.route('/set_duration/<filename>', methods=['POST'])
def set_duration(filename):
    g = perm_guard('duration')
    if g: return g
    filename = os.path.basename(filename)
    data     = request.json or {}
    cfg      = load_config()
    screen   = normalize_screen_key(data.get('screen', ''), cfg)
    if _is_generated_menu_video(cfg, filename):
        return jsonify({"error": "menu video duration is locked"}), 403
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    try:
        duration = int(data.get('duration', 15))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid duration"}), 400
    if duration < 1 or duration > 3600:
        return jsonify({"error": "invalid duration"}), 400
    screen_cfg = get_screen_config(cfg, screen)
    if screen_cfg is None:
        return jsonify({"error": "screen not found"}), 404
    screen_cfg.setdefault('durations', {})[filename] = duration

    _propagate_broadcast(screen, cfg)
    save_config(cfg)
    log_activity(session.get('user'), 'config', filename=filename,
                 details=f'duration={duration}s ({_scope_details(screen)})')
    return jsonify({"ok": True})


@bp.route('/reorder', methods=['POST'])
def reorder():
    g = perm_guard('reorder')
    if g: return g
    data   = request.json or {}
    cfg   = load_config()
    screen = normalize_screen_key(data.get('screen', ''), cfg)
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    order = data.get('order', [])
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        return jsonify({"error": "invalid order"}), 400
    valid_files = set(get_all_media())
    order = [item for item in order if item in valid_files]

    screen_cfg = get_screen_config(cfg, screen)
    if screen_cfg is None:
        return jsonify({"error": "screen not found"}), 404
    screen_cfg['order'] = order

    _propagate_broadcast(screen, cfg)
    save_config(cfg)
    log_activity(session.get('user'), 'config', details=f'order updated ({len(order)} media, {_scope_details(screen)})')
    return jsonify({"ok": True})


@bp.route('/schedule/<path:filename>', methods=['POST'])
def set_schedule(filename):
    g = perm_guard('schedule')
    if g: return g
    g = feature_guard_json('schedule')
    if g: return g
    filename = os.path.basename(filename)
    data     = request.get_json(silent=True) or {}
    cfg = load_config()
    screen   = normalize_screen_key(data.get('screen', ''), cfg)
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    schedules = _get_schedule_bucket(cfg, screen)
    if schedules is None:
        return jsonify({"error": "screen not found"}), 404

    sched = _build_schedule_payload(data)
    if sched is None:
        return jsonify({"error": "invalid schedule"}), 400

    if sched:
        schedules[filename] = sched
    elif filename in schedules:
        del schedules[filename]
    _propagate_broadcast(screen, cfg)
    save_config(cfg)
    log_activity(session.get('user'), 'config', filename=filename,
                 details=f'schedule updated ({_scope_details(screen)}): {_schedule_details(sched)}')
    return jsonify({"ok": True})


@bp.route('/programming/save', methods=['POST'])
def save_programming():
    g = perm_guard('schedule')
    if g:
        return g
    g = feature_guard_json('schedule')
    if g:
        return g

    data = request.get_json(silent=True) or {}
    filename = os.path.basename(str(data.get('filename', '')).strip())
    original_filename = os.path.basename(str(data.get('original_filename', filename)).strip())
    cfg = load_config()
    screen = normalize_screen_key(data.get('screen', ''), cfg)
    original_screen = normalize_screen_key(data.get('original_screen', screen), cfg)

    if not filename:
        return jsonify({"ok": False, "error": "missing filename"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"ok": False, "error": "screen access denied"}), 403
    if original_screen and not has_screen_access(original_screen):
        return jsonify({"ok": False, "error": "screen access denied"}), 403

    target_bucket = _get_schedule_bucket(cfg, screen)
    source_bucket = _get_schedule_bucket(cfg, original_screen)
    if target_bucket is None or source_bucket is None:
        return jsonify({"ok": False, "error": "screen not found"}), 404

    sched = _build_schedule_payload(data)
    if sched is None:
        return jsonify({"ok": False, "error": "invalid schedule"}), 400
    if not sched:
        return jsonify({"ok": False, "error": "empty schedule"}), 400

    if original_filename and (original_filename != filename or original_screen != screen):
        source_bucket.pop(original_filename, None)
    target_bucket[filename] = sched
    save_config(cfg)
    log_activity(
        session.get('user'),
        'config',
        filename=filename,
        details=f'schedule saved ({_scope_details(screen)}): {_schedule_details(sched)}',
    )
    return jsonify({"ok": True})


@bp.route('/programming/delete', methods=['POST'])
def delete_programming():
    g = perm_guard('schedule')
    if g:
        return g
    g = feature_guard_json('schedule')
    if g:
        return g

    data = request.get_json(silent=True) or {}
    filename = os.path.basename(str(data.get('filename', '')).strip())
    cfg = load_config()
    screen = normalize_screen_key(data.get('screen', ''), cfg)
    if not filename:
        return jsonify({"ok": False, "error": "missing filename"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"ok": False, "error": "screen access denied"}), 403

    bucket = _get_schedule_bucket(cfg, screen)
    if bucket is None:
        return jsonify({"ok": False, "error": "screen not found"}), 404

    bucket.pop(filename, None)
    save_config(cfg)
    log_activity(session.get('user'), 'config', filename=filename,
                 details=f'schedule deleted ({_scope_details(screen)})')
    return jsonify({"ok": True})
