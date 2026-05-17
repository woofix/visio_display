# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import queue
import sys
import threading

from flask import Response, current_app, flash, jsonify, redirect, request, send_file, session, stream_with_context

from blueprints.guards import superadmin_guard
from services.activity_svc import log_config_change
from services.backup_svc import (
    backup_path,
    create_backup_archive,
    delete_backup_archive,
    list_backups,
    prune_old_backups,
    restore_backup_archive,
    test_smb_destination,
)
from services.config_svc import load_config, save_config
from services.backup_scheduler_svc import save_backup_schedule
from services.i18n import _flash, _t
from services.settings_sections import settings_section_url

from . import bp


def _build_backup_remote_settings_from_form(current_settings=None):
    current_settings = current_settings or {}
    password = str(request.form.get('password', '') or '').strip()
    return {
        'enabled': request.form.get('enabled') == 'on',
        'url': str(request.form.get('url', '') or '').strip(),
        'username': str(request.form.get('username', '') or '').strip(),
        'password': password if password else str(current_settings.get('password', '') or '').strip(),
    }


@bp.route('/admin/settings/backups/create', methods=['POST'])
def create_backup():
    redir = superadmin_guard()
    if redir:
        return redir

    backup = create_backup_archive()
    log_config_change(session.get('user'), f"backup created: {backup['filename']}")
    _flash('flash_backup_created', 'success', filename=backup['filename'])
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/remote', methods=['POST'])
def save_backup_remote():
    redir = superadmin_guard()
    if redir:
        return redir

    cfg = load_config()
    remote_settings = _build_backup_remote_settings_from_form(cfg.get('backup_remote', {}))
    if remote_settings['enabled'] and not remote_settings['url']:
        _flash('flash_backup_remote_missing_url', 'error')
        return redirect(settings_section_url('sauvegardes'))
    if remote_settings['url'] and not remote_settings['url'].lower().startswith('smb://'):
        _flash('flash_backup_remote_invalid_url', 'error')
        return redirect(settings_section_url('sauvegardes'))

    cfg['backup_remote'] = remote_settings
    save_config(cfg)
    log_config_change(
        session.get('user'),
        f"backup SMB destination updated: active={'yes' if remote_settings['enabled'] else 'no'}, url={remote_settings['url'] or '-'}",
    )
    _flash('flash_backup_remote_saved', 'success')
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/schedule', methods=['POST'])
def save_backup_schedule_route():
    redir = superadmin_guard()
    if redir:
        return redir

    try:
        schedule = save_backup_schedule({
            'enabled': request.form.get('enabled') == 'on',
            'time': str(request.form.get('time', '') or '').strip(),
            'copy_to_smb': request.form.get('copy_to_smb') == 'on',
        })
    except ValueError:
        _flash('flash_backup_schedule_invalid_time', 'error')
        return redirect(settings_section_url('sauvegardes'))

    log_config_change(
        session.get('user'),
        (
            f"backup automation updated: active={'yes' if schedule['enabled'] else 'no'}, "
            f"time={schedule['time']}, smb={'yes' if schedule['copy_to_smb'] else 'no'}"
        ),
    )
    _flash('flash_backup_schedule_saved', 'success')
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/retention', methods=['POST'])
def save_backup_retention():
    redir = superadmin_guard()
    if redir:
        return redir

    try:
        max_versions = min(365, max(1, int(request.form.get('max_versions', 5))))
    except (TypeError, ValueError):
        _flash('flash_backup_retention_invalid', 'error')
        return redirect(settings_section_url('sauvegardes'))

    cfg = load_config()
    cfg['backup_retention'] = {'max_versions': max_versions}
    save_config(cfg)
    prune_old_backups()
    log_config_change(session.get('user'), f"backup retention updated: {max_versions} versions")
    _flash('flash_backup_retention_saved', 'success')
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/remote/test-stream', methods=['POST'])
def test_backup_remote_stream():
    redir = superadmin_guard()
    if redir:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    cfg = load_config()
    remote_settings = _build_backup_remote_settings_from_form(cfg.get('backup_remote', {}))
    if not remote_settings.get('url'):
        return jsonify({'ok': False, 'error': _t('flash_backup_remote_missing_url')}), 400
    if not remote_settings['url'].lower().startswith('smb://'):
        return jsonify({'ok': False, 'error': _t('flash_backup_remote_invalid_url')}), 400

    app = current_app._get_current_object()
    events = queue.Queue()
    done = threading.Event()

    def emit(event_type, **payload):
        events.put({'type': event_type, **payload})

    def worker():
        try:
            with app.app_context():
                test_smb_destination(
                    remote_settings,
                    progress_callback=lambda message: emit('log', message=message),
                )
            emit('done')
        except Exception as exc:
            emit('error', message=str(exc) or exc.__class__.__name__)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield json.dumps({'type': 'log', 'message': 'Connecting to SMB test engine...'}) + '\n'
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload) + '\n'

    return Response(generate(), mimetype='application/x-ndjson')


@bp.route('/admin/settings/backups/create-stream', methods=['POST'])
def create_backup_stream():
    redir = superadmin_guard()
    if redir:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    app = current_app._get_current_object()
    username = session.get('user')
    events = queue.Queue()
    done = threading.Event()

    def emit(event_type, **payload):
        events.put({'type': event_type, **payload})

    def serialize_backup(backup):
        return {
            'filename': backup.get('filename'),
            'size': backup.get('size'),
            'size_bytes': backup.get('size_bytes'),
            'created_at_iso': backup.get('created_at_iso'),
        }

    def worker():
        try:
            with app.app_context():
                backup = create_backup_archive(progress_callback=lambda message: emit('log', message=message))
                log_config_change(username, f"backup created: {backup['filename']}")
                backups = [serialize_backup(item) for item in list_backups()]
            emit('done', backup=serialize_backup(backup), backups=backups)
        except Exception as exc:
            emit('error', message=str(exc) or exc.__class__.__name__)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield json.dumps({'type': 'log', 'message': 'Connecting to backup engine...'}) + '\n'
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload) + '\n'

    return Response(generate(), mimetype='application/x-ndjson')


@bp.route('/admin/settings/backups/list')
def list_backup_archives():
    redir = superadmin_guard()
    if redir:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    return jsonify({
        'ok': True,
        'backups': [
            {
                'filename': item.get('filename'),
                'size': item.get('size'),
                'size_bytes': item.get('size_bytes'),
                'created_at_iso': item.get('created_at_iso'),
            }
            for item in list_backups()
        ],
    })


@bp.route('/admin/settings/backups/copy-stream/<filename>', methods=['POST'])
def copy_backup_stream(filename):
    redir = superadmin_guard()
    if redir:
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    cfg = load_config()
    remote_settings = cfg.get('backup_remote', {})
    if not remote_settings.get('enabled') or not remote_settings.get('url'):
        return jsonify({'ok': False, 'error': _t('flash_backup_remote_not_configured')}), 400

    try:
        path = backup_path(filename)
    except FileNotFoundError:
        return jsonify({'ok': False, 'error': _t('flash_backup_delete_missing')}), 404

    app = current_app._get_current_object()
    username = session.get('user')
    events = queue.Queue()
    done = threading.Event()

    def emit(event_type, **payload):
        events.put({'type': event_type, **payload})

    def worker():
        try:
            with app.app_context():
                sys.modules['blueprints.settings'].copy_backup_to_smb(
                    path,
                    filename,
                    remote_settings,
                    progress_callback=lambda message: emit('log', message=message),
                )
                log_config_change(username, f"backup copied to SMB: {filename}")
            emit('done', filename=filename)
        except Exception as exc:
            emit('error', message=str(exc) or exc.__class__.__name__)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    @stream_with_context
    def generate():
        yield json.dumps({'type': 'log', 'message': 'Connecting to SMB copy engine...'}) + '\n'
        while not done.is_set() or not events.empty():
            try:
                payload = events.get(timeout=0.2)
            except queue.Empty:
                continue
            yield json.dumps(payload) + '\n'

    return Response(generate(), mimetype='application/x-ndjson')


@bp.route('/admin/settings/backups/download/<filename>')
def download_backup(filename):
    redir = superadmin_guard()
    if redir:
        return redir
    path = backup_path(filename)
    return send_file(path, as_attachment=True, download_name=filename)


@bp.route('/admin/settings/backups/copy/<filename>', methods=['POST'])
def copy_backup(filename):
    redir = superadmin_guard()
    if redir:
        return redir

    cfg = load_config()
    remote_settings = cfg.get('backup_remote', {})
    if not remote_settings.get('enabled') or not remote_settings.get('url'):
        _flash('flash_backup_remote_not_configured', 'error')
        return redirect(settings_section_url('sauvegardes'))

    try:
        path = backup_path(filename)
        sys.modules['blueprints.settings'].copy_backup_to_smb(path, filename, remote_settings)
    except FileNotFoundError:
        _flash('flash_backup_delete_missing', 'error')
    except Exception as exc:
        flash(str(exc) or _t('backup_stream_error'), 'error')
    else:
        log_config_change(session.get('user'), f"backup copied to SMB: {filename}")
        _flash('flash_backup_copied', 'success', filename=filename)
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/delete/<filename>', methods=['POST'])
def delete_backup(filename):
    redir = superadmin_guard()
    if redir:
        return redir

    try:
        delete_backup_archive(filename)
    except FileNotFoundError:
        _flash('flash_backup_delete_missing', 'error')
    else:
        log_config_change(session.get('user'), f"backup deleted: {filename}")
        _flash('flash_backup_deleted', 'success', filename=filename)
    return redirect(settings_section_url('sauvegardes'))


@bp.route('/admin/settings/backups/restore', methods=['POST'])
def restore_backup():
    redir = superadmin_guard()
    if redir:
        return redir

    uploaded = request.files.get('backup_file')
    if uploaded is None or not uploaded.filename:
        _flash('flash_backup_file_missing', 'error')
        return redirect(settings_section_url('sauvegardes'))

    try:
        restore_backup_archive(uploaded)
    except Exception as exc:
        flash(str(exc) or _t('flash_backup_restore_failed'), 'error')
        return redirect(settings_section_url('sauvegardes'))

    log_config_change(session.get('user'), f"backup restored: {uploaded.filename}")
    _flash('flash_backup_restored', 'success', filename=uploaded.filename)
    return redirect(settings_section_url('sauvegardes'))
