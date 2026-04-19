import os

from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify

from constants import UPLOAD_FOLDER, VIDEO_EXTS
from services.config_svc import load_config, save_config
from services.users_svc import load_users, has_permission, has_screen_access, is_superadmin
from services.media_svc import (
    get_all_media, get_file_info, get_logo_path,
    clean_filename, is_h264_mp4, get_media_groups,
    collect_group_states, is_media_disabled, normalize_group_name,
    get_group_active_screens,
)
from services.queue_svc import load_queue, save_queue, enqueue_upload_job
from services.i18n import _flash
from services.activity_svc import log_activity
from blueprints.guards import admin_guard, perm_guard

bp = Blueprint('media', __name__)


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
        logo_path=get_logo_path(), can_schedule=has_permission('schedule'),
        current_user_is_superadmin=is_superadmin())


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
        ext      = os.path.splitext(filename)[1].lower()
        dest     = os.path.join(UPLOAD_FOLDER, filename)

        if ext == '.pdf':
            from pdf2image import convert_from_path
            file.save(dest)
            images = convert_from_path(dest)
            for i, img in enumerate(images):
                img_path = dest.replace('.pdf', f'_page_{i+1}.jpg')
                img.save(img_path, 'JPEG', quality=95)
            os.remove(dest)
            log_activity(session.get('user'), 'upload', filename=filename, details='pdf→jpg')

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
    return jsonify({"state": state})


@bp.route('/set_groups/<filename>', methods=['POST'])
def set_groups(filename):
    g = perm_guard('toggle')
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
    duration = data.get('duration', 15)
    cfg      = load_config()

    if screen and screen in cfg.get('screens', {}):
        cfg['screens'][screen].setdefault('durations', {})[filename] = int(duration)
    else:
        cfg.setdefault('durations', {})[filename] = int(duration)

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
    cfg   = load_config()

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
    filename = os.path.basename(filename)
    data     = request.get_json(silent=True) or {}
    screen   = str(data.get('screen', '')).strip().lower()
    if screen and not has_screen_access(screen):
        return jsonify({"error": "screen access denied"}), 403
    cfg = load_config()

    if screen and screen in cfg.get('screens', {}):
        schedules = cfg['screens'][screen].setdefault('schedules', {})
    else:
        schedules = cfg.setdefault('schedules', {})

    sched = {}
    for k in ("time_start", "time_end", "date_start", "date_end"):
        v = str(data.get(k, "")).strip()
        if v:
            sched[k] = v
    if sched:
        schedules[filename] = sched
    elif filename in schedules:
        del schedules[filename]
    save_config(cfg)
    return jsonify({"ok": True})
