import os
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.config_svc import load_config, save_config
from services.users_svc import load_users, has_permission, has_screen_access, is_superadmin
from services.media_svc import (
    get_all_media, get_file_info, get_logo_path,
    clean_filename, is_h264_mp4, get_media_groups,
    collect_group_states, is_media_disabled, normalize_group_name,
    ensure_unique_filename, is_valid_uploaded_image,
)
from services.schedule_svc import analyze_schedule_week, build_schedule_entries, parse_iso_date, parse_time_to_minutes, schedule_summary, start_of_week, week_days
from services.queue_svc import load_queue, save_queue, enqueue_upload_job
from services.i18n import _flash
from services.activity_svc import log_activity
from blueprints.guards import admin_guard, perm_guard, feature_guard, feature_guard_json

bp = Blueprint('media', __name__)


def _allowed_screens(cfg):
    return [screen for screen in cfg.get('screens', {}).keys() if has_screen_access(screen)]


def _resolve_schedule_bucket(cfg, screen, create=False):
    screen = str(screen or '').strip().lower()
    if screen:
        if screen not in cfg.get('screens', {}):
            return None
        if create:
            return cfg['screens'][screen].setdefault('schedules', {})
        return cfg['screens'][screen].get('schedules', {})
    if create:
        return cfg.setdefault('schedules', {})
    return cfg.get('schedules', {})


def _extract_schedule_payload(data, allow_empty=False):
    sched = {}
    for key in ("time_start", "time_end", "date_start", "date_end"):
        value = str(data.get(key, "")).strip()
        if value:
            sched[key] = value

    for time_key in ("time_start", "time_end"):
        if time_key in sched and parse_time_to_minutes(sched[time_key]) is None:
            return None, "invalid schedule"

    start_minutes = parse_time_to_minutes(sched.get("time_start"))
    end_minutes = parse_time_to_minutes(sched.get("time_end"))
    if start_minutes is not None and end_minutes is not None and end_minutes < start_minutes:
        return None, "invalid schedule"

    for date_key in ("date_start", "date_end"):
        if date_key in sched and parse_iso_date(sched[date_key]) is None:
            return None, "invalid schedule"

    date_start = parse_iso_date(sched.get("date_start"))
    date_end = parse_iso_date(sched.get("date_end"))
    if date_start and date_end and date_end < date_start:
        return None, "invalid schedule"

    if not sched and not allow_empty:
        return None, "missing schedule"
    return sched, None


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
        users=list(users.keys()), current_user=session.get('user'),
        logo_path=get_logo_path(), can_toggle=has_permission('toggle'),
        can_schedule=has_permission('schedule'),
        current_user_is_superadmin=is_superadmin())


@bp.route('/admin/programming')
def admin_programming():
    redir = admin_guard()
    if redir:
        return redir
    feature_redir = feature_guard('schedule')
    if feature_redir:
        return feature_redir

    cfg = load_config()
    all_media = get_all_media()
    infos = {filename: get_file_info(filename) for filename in all_media}
    screens = _allowed_screens(cfg)
    default_screen_name = cfg.get('default_screen_name') or 'Défaut'

    requested_day = parse_iso_date(request.args.get('week', '').strip()) or datetime.now().date()
    week_start = start_of_week(requested_day)
    week_end = week_start + timedelta(days=6)

    entries = build_schedule_entries(cfg, infos, screens, default_screen_name)
    analysis = analyze_schedule_week(entries, week_start)
    issue_counts = analysis.get('entry_issue_counts', {})
    for row in analysis.get('calendar_rows', []):
        row['item_count'] = sum(len(cell.get('items', [])) for cell in row.get('cells', []))

    for entry in entries:
        issues = issue_counts.get(entry['id'], {})
        entry['summary'] = schedule_summary(entry)
        entry['groups_label'] = ", ".join(entry['groups']) if entry['groups'] else "Sans groupe"
        entry['overlap_count'] = issues.get('overlaps', 0)

    day_names = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
    week_labels = []
    for index, day in enumerate(week_days(week_start)):
        week_labels.append({
            'iso': day.isoformat(),
            'label': f'{day_names[index]} {day.day:02d}/{day.month:02d}',
        })

    groups = sorted({group for entry in entries for group in entry['groups']}, key=str.casefold)
    users = load_users()

    return render_template(
        'admin_programming.html',
        entries=entries,
        current_screen='',
        screens=screens,
        screen_choices=[('', default_screen_name)] + [(screen, screen) for screen in screens],
        filter_screen_choices=[('__global__', default_screen_name)] + [(screen, screen) for screen in screens],
        media_choices=all_media,
        group_choices=groups,
        calendar_rows=analysis.get('calendar_rows', []),
        week_start=week_start.isoformat(),
        week_end=week_end.isoformat(),
        previous_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        week_labels=week_labels,
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
        log_activity(session.get('user'), 'delete', filename=filename)
        cfg = load_config()
        cfg["order"]    = [f for f in cfg.get("order", [])    if f != filename]
        cfg["disabled"] = [f for f in cfg.get("disabled", []) if f != filename]
        cfg["durations"].pop(filename, None)
        cfg.get("groups", {}).pop(filename, None)
        cfg.get("schedules", {}).pop(filename, None)
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

    upload_job_ids = []
    for file in files:
        if not file or file.filename == '':
            continue
        filename = clean_filename(file.filename)
        if not filename:
            continue
        ext      = os.path.splitext(filename)[1].lower()
        allowed_exts = VIDEO_EXTS + ('.pdf', '.jpg', '.jpeg', '.png')
        if ext not in allowed_exts:
            return jsonify({"error": "unsupported file type"}), 400
        filename = ensure_unique_filename(UPLOAD_FOLDER, filename)
        dest     = os.path.join(UPLOAD_FOLDER, filename)

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
    schedules = _resolve_schedule_bucket(cfg, screen, create=True)
    if schedules is None:
        return jsonify({"error": "invalid screen"}), 400

    sched, error = _extract_schedule_payload(data, allow_empty=True)
    if error:
        return jsonify({"error": error}), 400
    if sched:
        schedules[filename] = sched
    elif filename in schedules:
        del schedules[filename]
    save_config(cfg)
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
        return jsonify({"error": "missing filename"}), 400
    if filename not in get_all_media():
        return jsonify({"error": "file not found"}), 404
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    if original_screen and not has_screen_access(original_screen):
        return jsonify({"error": "screen access denied"}), 403

    sched, error = _extract_schedule_payload(data, allow_empty=False)
    if error:
        return jsonify({"error": error}), 400

    cfg = load_config()
    target_bucket = _resolve_schedule_bucket(cfg, screen, create=True)
    source_bucket = _resolve_schedule_bucket(cfg, original_screen, create=False)
    if target_bucket is None:
        return jsonify({"error": "invalid screen"}), 400
    if source_bucket is None:
        return jsonify({"error": "invalid screen"}), 400

    if original_filename in source_bucket and (original_filename != filename or original_screen != screen):
        del source_bucket[original_filename]

    target_bucket[filename] = sched
    save_config(cfg)
    details = f'{filename} → {screen or "global"}'
    log_activity(session.get('user'), 'schedule', filename=filename, details=details)
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
        return jsonify({"error": "missing filename"}), 400
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403

    cfg = load_config()
    bucket = _resolve_schedule_bucket(cfg, screen, create=False)
    if bucket is None:
        return jsonify({"error": "invalid screen"}), 400
    if filename in bucket:
        del bucket[filename]
        save_config(cfg)
        log_activity(session.get('user'), 'schedule', filename=filename, details=f'suppression → {screen or "global"}')
    return jsonify({"ok": True})
