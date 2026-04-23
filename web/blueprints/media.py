# MIT License - Copyright (c) 2026 Woofix
# See LICENSE file for details

import json
import os
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

import constants as C
from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.config_svc import load_config, save_config, get_default_screen_name
from services.users_svc import load_users, has_permission, has_screen_access, is_superadmin
from services.media_svc import (
    get_all_media, get_file_info, get_logo_path,
    clean_filename, is_h264_mp4, get_media_groups,
    collect_group_states, is_media_disabled, normalize_group_name,
    ensure_unique_filename, is_valid_uploaded_image,
    build_media_preview_map, delete_image_variants, delete_media_thumbnail, delete_video_variants,
    generate_standard_renditions,
    get_media_url, get_original_media_url,
)
from services.queue_svc import load_queue, save_queue, enqueue_upload_job
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

MAX_FILE_UPLOAD_SIZE = getattr(C, 'MAX_FILE_UPLOAD_SIZE', 16 * 1024 * 1024)
MAX_BATCH_UPLOAD_SIZE = getattr(C, 'MAX_BATCH_UPLOAD_SIZE', 256 * 1024 * 1024)


def _get_uploaded_file_size(file_storage):
    stream = getattr(file_storage, 'stream', None)
    if stream is None:
        return 0
    try:
        current = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current)
        return size
    except (AttributeError, OSError):
        return 0


def _get_schedule_bucket(cfg, screen):
    screen = str(screen or '').strip().lower()
    if screen:
        if screen not in cfg.get('screens', {}):
            return None
        return cfg['screens'][screen].setdefault('schedules', {})
    return cfg.setdefault('schedules', {})


def _normalize_conflict_strategy(raw_value):
    value = str(raw_value or '').strip().lower()
    return value if value in {'rename_custom', 'overwrite'} else ''


def _load_rename_map():
    try:
        payload = json.loads(request.form.get('rename_map', '{}') or '{}')
    except (TypeError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        str(source).strip(): clean_filename(str(target))
        for source, target in payload.items()
        if str(source).strip() and clean_filename(str(target))
    }


def _collect_upload_name_conflicts(files):
    conflicts = []
    seen = set()
    for index, file in enumerate(files):
        if not file or not file.filename:
            continue
        filename = clean_filename(file.filename)
        if not filename:
            continue
        path_exists = os.path.exists(os.path.join(UPLOAD_FOLDER, filename))
        duplicate_in_batch = filename in seen
        if path_exists or duplicate_in_batch:
            conflicts.append({
                "upload_index": index,
                "filename": filename,
            })
        seen.add(filename)
    return conflicts


def _prepare_overwrite_target(filename):
    path = os.path.join(UPLOAD_FOLDER, filename)
    delete_media_thumbnail(filename)
    delete_image_variants(filename)
    delete_video_variants(filename)
    if os.path.exists(path):
        os.remove(path)


def _resolve_custom_rename(file_index, filename, rename_map):
    target = rename_map.get(str(file_index), '')
    if not target:
        return None, "missing rename"
    source_ext = os.path.splitext(filename)[1].lower()
    target_root, target_ext = os.path.splitext(target)
    if not target_ext:
        target = f"{target_root}{source_ext}"
        target_ext = source_ext
    if target_ext.lower() != source_ext:
        return None, "extension mismatch"
    return target, None


def _scope_details(screen):
    return f'écran:{screen}' if screen else 'global'


def _schedule_details(sched):
    parts = []
    for key in ('time_start', 'time_end', 'date_start', 'date_end'):
        value = sched.get(key)
        if value:
            parts.append(f'{key}={value}')
    return ', '.join(parts) if parts else 'aucune règle'


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
    screen    = request.args.get('screen', '').strip().lower()
    all_media = get_all_media()
    infos     = {f: get_file_info(f) for f in all_media}
    q         = load_queue()
    queued    = {j['filename'] for j in q if j['status'] in ('pending', 'processing')}
    users     = load_users()
    screens   = [s for s in cfg.get('screens', {}).keys() if has_screen_access(s)]

    if screen and screen in cfg.get('screens', {}):
        scfg         = cfg['screens'][screen]
        assigned_set = set(scfg.get('order', []))
        files        = [f for f in scfg.get('order', []) if f in set(all_media)]
        unassigned   = [f for f in all_media if f not in assigned_set]
        view_cfg     = {'disabled': scfg.get('disabled', []),
                        'disabled_groups': scfg.get('disabled_groups', []),
                        'durations': scfg.get('durations', {})}
        schedules    = scfg.get('schedules', {})
    else:
        screen     = ''
        files      = all_media
        unassigned = []
        view_cfg   = cfg
        schedules  = cfg.get('schedules', {})

    media_groups = {f: get_media_groups(f, cfg) for f in all_media}
    preview_urls = build_media_preview_map(all_media, context='admin')
    preview_media_urls = {
        filename: get_media_url(
            filename,
            context='preview',
            allow_original=True,
            generate_missing=True,
        ) or get_original_media_url(filename)
        for filename in all_media
    }
    effective_cfg = dict(view_cfg)
    effective_cfg['groups'] = cfg.get('groups', {})
    effective_cfg['group_pools'] = cfg.get('group_pools', {})
    effective_cfg['group_screens'] = cfg.get('group_screens', {})
    group_states = collect_group_states(files, effective_cfg, screen=screen)
    disabled_map = {f: is_media_disabled(f, effective_cfg) for f in files}

    return render_template('admin_media.html',
        files=files, unassigned=unassigned, infos=infos, cfg=view_cfg, queued=queued,
        schedules=schedules, current_screen=screen, screens=screens,
        media_groups=media_groups, group_states=group_states, disabled_map=disabled_map,
        preview_urls=preview_urls, preview_media_urls=preview_media_urls,
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path(), can_toggle=has_permission('toggle'),
        can_schedule=has_permission('schedule'),
        current_user_is_superadmin=is_superadmin())


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
    media_infos = {filename: get_file_info(filename) for filename in files}
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
        entry['summary'] = schedule_summary(entry)
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

    screen_choices = [('', default_screen_name)] + [(screen, screen) for screen in allowed_screens]
    filter_screen_choices = [('__global__', default_screen_name)] + [(screen, screen) for screen in allowed_screens]
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
        logo_path=get_logo_path())


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
        save_campaigns_to_config(cfg, cleanup_campaigns_for_deleted_media(get_campaigns(cfg), filename))
        for scfg in cfg.get('screens', {}).values():
            scfg['order']    = [f for f in scfg.get('order', [])    if f != filename]
            scfg['disabled'] = [f for f in scfg.get('disabled', []) if f != filename]
            scfg.get('durations', {}).pop(filename, None)
            scfg.get('schedules', {}).pop(filename, None)
        save_config(cfg)
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
    files = request.files.getlist('file')
    if not files:
        _flash('flash_no_file', 'error')
        return redirect(url_for('admin.admin_page'))
    conflict_strategy = _normalize_conflict_strategy(request.form.get('conflict_strategy'))
    rename_map = _load_rename_map()
    if not conflict_strategy:
        conflicts = _collect_upload_name_conflicts(files)
        if conflicts:
            return jsonify({"error": "name conflict", "conflicts": conflicts}), 409

    total_size = sum(_get_uploaded_file_size(file) for file in files if file and file.filename)
    if total_size > MAX_BATCH_UPLOAD_SIZE:
        return jsonify({"error": "batch too large"}), 400

    upload_job_ids = []
    planned_filenames = set()
    for file_index, file in enumerate(files):
        if not file or file.filename == '':
            continue
        if _get_uploaded_file_size(file) > MAX_FILE_UPLOAD_SIZE:
            return jsonify({"error": "file too large"}), 400
        filename = clean_filename(file.filename)
        if not filename:
            continue
        ext      = os.path.splitext(filename)[1].lower()
        allowed_exts = VIDEO_EXTS + ('.pdf', '.jpg', '.jpeg', '.png')
        if ext not in allowed_exts:
            return jsonify({"error": "unsupported file type"}), 400

        path_exists = os.path.exists(os.path.join(UPLOAD_FOLDER, filename))
        duplicate_in_batch = filename in planned_filenames
        needs_rename = path_exists or duplicate_in_batch

        if conflict_strategy == 'rename_custom' and needs_rename:
            renamed_filename, rename_error = _resolve_custom_rename(file_index, filename, rename_map)
            if rename_error:
                return jsonify({"error": rename_error, "filename": filename}), 400
            if (
                renamed_filename in planned_filenames
                or os.path.exists(os.path.join(UPLOAD_FOLDER, renamed_filename))
            ):
                return jsonify({
                    "error": "name conflict",
                    "conflicts": [{
                        "upload_index": file_index,
                        "filename": filename,
                    }],
                    "message": f"Le nom choisi existe déjà : {rename_map.get(str(file_index), filename)}",
                }), 409
            filename = renamed_filename
        elif conflict_strategy == 'overwrite' and path_exists:
            _prepare_overwrite_target(filename)
        elif needs_rename:
            return jsonify({
                "error": "name conflict",
                "conflicts": [{
                    "upload_index": file_index,
                    "filename": filename,
                }],
            }), 409
        dest     = os.path.join(UPLOAD_FOLDER, filename)
        planned_filenames.add(filename)

        if ext == '.pdf':
            from pdf2image import convert_from_path
            file.save(dest)
            try:
                images = convert_from_path(dest)
                for i, img in enumerate(images):
                    img_path = dest.replace('.pdf', f'_page_{i+1}.jpg')
                    img.save(img_path, 'JPEG', quality=95)
                log_activity(session.get('user'), 'upload', filename=filename, details='pdf→jpg')
            finally:
                if os.path.exists(dest):
                    os.remove(dest)

        elif ext in VIDEO_EXTS:
            tmp = dest + '.tmp' + ext
            file.save(tmp)
            if ext == '.mp4' and is_h264_mp4(tmp):
                os.replace(tmp, dest)
                generate_standard_renditions(filename)
                log_activity(session.get('user'), 'upload', filename=filename)
            else:
                final_name = os.path.basename(os.path.splitext(dest)[0] + '.mp4')
                out        = os.path.join(UPLOAD_FOLDER, final_name)
                job_id     = enqueue_upload_job(tmp, out, final_name)
                upload_job_ids.append({"id": job_id, "filename": final_name})
                log_activity(session.get('user'), 'upload', filename=final_name, details='encoding')

        else:
            file.save(dest)
            if not is_valid_uploaded_image(dest):
                os.remove(dest)
                return jsonify({"error": "invalid image file"}), 400
            generate_standard_renditions(filename)
            log_activity(session.get('user'), 'upload', filename=filename)

    return jsonify({"ok": True, "jobs": upload_job_ids, "redirect": "/admin/media"})


@bp.route('/toggle/<filename>', methods=['POST'])
def toggle_file(filename):
    g = perm_guard('toggle')
    if g: return g
    filename = os.path.basename(filename)
    data     = request.get_json(silent=True) or {}
    screen   = data.get('screen', '').strip().lower()
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    cfg = load_config()

    if screen and screen in cfg.get('screens', {}):
        disabled = cfg['screens'][screen].setdefault('disabled', [])
    else:
        disabled = cfg.setdefault('disabled', [])

    if filename in disabled:
        disabled.remove(filename)
        state = "enabled"
    else:
        disabled.append(filename)
        state = "disabled"

    save_config(cfg)
    details = state + (' → ' + screen if screen else '')
    log_activity(session.get('user'), 'toggle', filename=filename, details=details)
    return jsonify({"state": state})


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

    save_config(cfg)
    details = f'groupes={", ".join(groups)}' if groups else 'groupes supprimés'
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
    valid_screens = set(cfg.get('screens', {}).keys()) | {''}
    screens_list = [s for s in screens_list if s in valid_screens]
    group_screens = cfg.setdefault('group_screens', {})
    if screens_list:
        group_screens[normalized] = screens_list
    else:
        group_screens.pop(normalized, None)
    save_config(cfg)
    details = f'affectation groupe {normalized}: {", ".join(screens_list) if screens_list else "tous les écrans"}'
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
    details = f'pool groupe {normalized}: {pool_size}' if pool_size > 0 else f'pool groupe {normalized} supprimé'
    log_activity(session.get('user'), 'config', details=details)
    return jsonify({"ok": True, "group": normalized, "pool_size": pool_size})


@bp.route('/toggle_group/<path:group_name>', methods=['POST'])
def toggle_group(group_name):
    g = perm_guard('toggle')
    if g: return g
    g = feature_guard_json('groups')
    if g: return g
    data = request.get_json(silent=True) or {}
    screen = data.get('screen', '').strip().lower()
    normalized_group = normalize_group_name(group_name)
    if not normalized_group:
        return jsonify({"error": "invalid group"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403

    cfg = load_config()
    if screen and screen in cfg.get('screens', {}):
        disabled_groups = cfg['screens'][screen].setdefault('disabled_groups', [])
    else:
        disabled_groups = cfg.setdefault('disabled_groups', [])

    if normalized_group in disabled_groups:
        disabled_groups.remove(normalized_group)
        state = "enabled"
    else:
        disabled_groups.append(normalized_group)
        state = "disabled"

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
    screen   = data.get('screen', '').strip().lower()
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    try:
        duration = int(data.get('duration', 15))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid duration"}), 400
    if duration < 1 or duration > 3600:
        return jsonify({"error": "invalid duration"}), 400
    cfg      = load_config()

    if screen and screen in cfg.get('screens', {}):
        cfg['screens'][screen].setdefault('durations', {})[filename] = duration
    else:
        cfg.setdefault('durations', {})[filename] = duration

    save_config(cfg)
    log_activity(session.get('user'), 'config', filename=filename,
                 details=f'durée={duration}s ({_scope_details(screen)})')
    return jsonify({"ok": True})


@bp.route('/reorder', methods=['POST'])
def reorder():
    g = perm_guard('reorder')
    if g: return g
    data   = request.json or {}
    screen = data.get('screen', '').strip().lower()
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    order = data.get('order', [])
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        return jsonify({"error": "invalid order"}), 400
    cfg   = load_config()
    valid_files = set(get_all_media())
    order = [item for item in order if item in valid_files]

    if screen and screen in cfg.get('screens', {}):
        cfg['screens'][screen]['order'] = order
    else:
        cfg['order'] = order

    save_config(cfg)
    log_activity(session.get('user'), 'config', details=f'ordre mis à jour ({len(order)} médias, {_scope_details(screen)})')
    return jsonify({"ok": True})


@bp.route('/schedule/<path:filename>', methods=['POST'])
def set_schedule(filename):
    g = perm_guard('schedule')
    if g: return g
    g = feature_guard_json('schedule')
    if g: return g
    filename = os.path.basename(filename)
    data     = request.get_json(silent=True) or {}
    screen   = str(data.get('screen', '')).strip().lower()
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    cfg = load_config()
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
    save_config(cfg)
    log_activity(session.get('user'), 'config', filename=filename,
                 details=f'programmation mise à jour ({_scope_details(screen)}): {_schedule_details(sched)}')
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
    screen = str(data.get('screen', '')).strip().lower()
    original_screen = str(data.get('original_screen', screen)).strip().lower()

    if not filename:
        return jsonify({"ok": False, "error": "missing filename"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"ok": False, "error": "screen access denied"}), 403
    if original_screen and not has_screen_access(original_screen):
        return jsonify({"ok": False, "error": "screen access denied"}), 403

    cfg = load_config()
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
        details=f'programmation enregistrée ({_scope_details(screen)}): {_schedule_details(sched)}',
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
    screen = str(data.get('screen', '')).strip().lower()
    if not filename:
        return jsonify({"ok": False, "error": "missing filename"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"ok": False, "error": "screen access denied"}), 403

    cfg = load_config()
    bucket = _get_schedule_bucket(cfg, screen)
    if bucket is None:
        return jsonify({"ok": False, "error": "screen not found"}), 404

    bucket.pop(filename, None)
    save_config(cfg)
    log_activity(session.get('user'), 'config', filename=filename,
                 details=f'programmation supprimée ({_scope_details(screen)})')
    return jsonify({"ok": True})
