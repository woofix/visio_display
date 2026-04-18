"""Forcer l'encodage de la file d'attente sans attendre la fenêtre nocturne.
Usage : docker exec Visio python encode_now.py
"""
import json
import os
import subprocess

UPLOAD_FOLDER = 'static/data'
QUEUE_FILE    = 'static/data/queue.json'
VIDEO_EXTS    = ('.mp4', '.webm', '.mov', '.avi', '.mkv')

def load_queue():
    if os.path.exists(QUEUE_FILE):
        with open(QUEUE_FILE) as f:
            return json.load(f)
    return []

def save_queue(q):
    with open(QUEUE_FILE, 'w') as f:
        json.dump(q, f, indent=2)

def reencode(src, dst):
    try:
        subprocess.run([
            'ffmpeg', '-i', src,
            '-vcodec', 'libx264', '-crf', '28', '-preset', 'veryfast',
            '-acodec', 'aac', '-b:a', '96k',
            '-movflags', '+faststart',
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
            '-y', dst
        ], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print('[FFMPEG]', e.stderr.decode())
        return False

q = load_queue()
pending = [j for j in q if j['status'] == 'pending']

if not pending:
    print('Aucun job en attente.')
    exit(0)

print(f'{len(pending)} job(s) en attente.\n')

for job in pending:
    print(f'→ {job["filename"]} ...')
    src = os.path.join(UPLOAD_FOLDER, job['filename'])
    if not os.path.exists(src):
        job['status'] = 'error'
        job['message'] = 'Fichier introuvable'
        print('  ✗ Fichier introuvable')
        continue

    size_before = os.path.getsize(src)
    tmp = src + '.tmp.mp4'
    out = os.path.splitext(src)[0] + '.mp4'

    ok = reencode(src, tmp)
    if ok:
        os.replace(tmp, out)
        if out != src:
            try:
                os.remove(src)
            except OSError:
                pass
        size_after = os.path.getsize(out)
        ratio = round(size_before / size_after, 1) if size_after else '?'
        new_name = os.path.basename(out)
        job['status']   = 'done'
        job['new_name'] = new_name
        job['before']   = round(size_before / 1024 / 1024, 1)
        job['after']    = round(size_after  / 1024 / 1024, 1)
        job['ratio']    = ratio
        print(f'  ✓ {job["before"]} Mo → {job["after"]} Mo (÷{ratio})')
        # Activation automatique
        cfg_path = 'static/data/config.json'
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
            if new_name in cfg.get('disabled', []):
                cfg['disabled'].remove(new_name)
            if new_name != job['filename']:
                for key in ('order', 'disabled'):
                    lst = cfg.get(key, [])
                    if job['filename'] in lst:
                        lst[lst.index(job['filename'])] = new_name
                        cfg[key] = lst
            with open(cfg_path, 'w') as f:
                json.dump(cfg, f, indent=2)
    else:
        try:
            os.remove(tmp)
        except OSError:
            pass
        job['status']  = 'error'
        job['message'] = 'Échec ffmpeg'
        print('  ✗ Échec ffmpeg')

save_queue(q)
print('\nTerminé.')
