const adminUploadConfigEl = document.getElementById('admin-upload-config');
const adminUploadConfig = adminUploadConfigEl ? JSON.parse(adminUploadConfigEl.textContent || '{}') : {};
const MSG_TOO_LARGE        = adminUploadConfig.tooLarge || '';
const MSG_TOO_LARGE_SINGLE = adminUploadConfig.tooLargeSingle || '';
const MSG_BATCH_TOO_LARGE  = adminUploadConfig.batchTooLarge || '';
const MSG_NETWORK_ERROR    = adminUploadConfig.networkError || '';
const MSG_ENCODING_TITLE   = adminUploadConfig.encodingTitle || '';
const MSG_ENCODING_DONE    = adminUploadConfig.encodingDone || '';
const MSG_ENCODING_ERROR   = adminUploadConfig.encodingError || '';
const MSG_INVALID_FORMAT   = adminUploadConfig.invalidFormat || '';
const MSG_ACCEPTED_FORMATS = adminUploadConfig.acceptedFormats || '';
const MSG_UPLOADING        = adminUploadConfig.uploading || '';
const MSG_UPLOADING_FILES  = adminUploadConfig.uploadingFiles || '';
const JS_WINDOW_ACTIVE   = adminUploadConfig.windowActive || '';
const JS_WINDOW_INACTIVE = adminUploadConfig.windowInactive || '';
const JS_TONIGHT         = adminUploadConfig.tonight || '';
const JS_TOMORROW        = adminUploadConfig.tomorrow || '';
const JS_PENDING         = adminUploadConfig.pending || '';
const JS_PROCESSING      = adminUploadConfig.processing || '';
const JS_DONE            = adminUploadConfig.done || '';
const JS_ERROR           = adminUploadConfig.error || '';
const JS_ADDED_ON        = adminUploadConfig.addedOn || '';
const JS_CANCEL_BTN      = adminUploadConfig.cancelBtn || '';
const JS_EMPTY_ACTIVE    = adminUploadConfig.emptyActive || '';
const JS_EMPTY_RECENT    = adminUploadConfig.emptyRecent || '';
const JS_CONFIRM_CANCEL  = adminUploadConfig.confirmCancel || '';
const MSG_FILE_TOO_LARGE   = adminUploadConfig.tooLargeSingle || '';
const QUEUE_FORCE_TITLE = adminUploadConfig.queueForceTitle || '';
const QUEUE_FORCE_CONFIRM = adminUploadConfig.queueForceConfirm || '';

const MSG_UNSUPPORTED_TYPE = adminUploadConfig.unsupportedType || 'Unsupported file type.';
const MSG_INVALID_IMAGE    = adminUploadConfig.invalidImage || 'The image file is invalid or corrupted.';
const MSG_UPLOAD_FAILED    = adminUploadConfig.uploadFailed || 'Upload failed. Check the file format and try again.';
const MSG_NAME_CONFLICT_TITLE = adminUploadConfig.conflictTitle || 'File already exists';
const MSG_NAME_CONFLICT_TEXT  = adminUploadConfig.conflictText || 'Choose the exact name to use for each conflicting file, or overwrite existing files.';
const MSG_NAME_CONFLICT_LIST  = adminUploadConfig.conflictList || 'Existing files';
const MSG_NAME_INPUT_LABEL    = adminUploadConfig.nameInputLabel || 'New name';
const MSG_NAME_CURRENT_LABEL  = adminUploadConfig.nameCurrentLabel || 'Current name';
const MSG_NAME_OCCURRENCE     = adminUploadConfig.nameOccurrence || 'Occurrence';
const MSG_NAME_INPUT_HELP     = adminUploadConfig.nameInputHelp || 'Keep the same extension.';
const MSG_NAME_REQUIRED       = adminUploadConfig.nameRequired || 'Please enter a name for each file.';
const MSG_NAME_EXT_MISMATCH   = adminUploadConfig.nameExtMismatch || 'The extension must remain identical to the original file.';
const MSG_NAME_DUPLICATE      = adminUploadConfig.nameDuplicate || 'Each new name must be unique.';
const MSG_NAME_EXISTS         = adminUploadConfig.nameExists || 'The selected name already exists. Choose another one.';
const MSG_NAME_RETRY          = adminUploadConfig.nameRetry || 'The selected name already exists. Edit it and try again.';
const MSG_NAME_MISSING        = adminUploadConfig.nameMissing || 'Missing name for a conflicting file.';
const UPLOAD_ANIMATION_MIN_MS = 900;
let uploadAnimationStartedAt = 0;
const ACCEPTED_EXTS = new Set(adminUploadConfig.acceptedExts || ['.jpg','.jpeg','.png','.pdf']);
const ACCEPTED_LABELS = adminUploadConfig.acceptedLabels || ['JPG','PNG','PDF'];

const uploadArea    = document.getElementById('upload-area');
const fileInput     = document.getElementById('file-input');
const preview       = document.getElementById('file-preview');
const progressWrap  = document.getElementById('progress-wrap');
const progressFill  = document.getElementById('progress-fill');
const encodePanel   = document.getElementById('encode-panel');
const encodeJobs    = document.getElementById('encode-jobs');
const rejectedBanner = document.getElementById('rejected-banner');
const overlayPct    = document.getElementById('overlay-pct');
const overlayTitle  = document.getElementById('overlay-title');
const overlaySub    = document.getElementById('overlay-sub');
let siteUploadOverlay = null;
let siteOverlayPct = null;
let siteOverlayTitle = null;
let siteOverlaySub = null;
const conflictModal = document.getElementById('upload-conflict-modal');
const conflictTitle = document.getElementById('upload-conflict-title');
const conflictHeadText = conflictModal.querySelector('.upload-conflict-head p');
const conflictBody = document.getElementById('upload-conflict-body');
const conflictCancelBtn = document.getElementById('upload-conflict-cancel');
const conflictOverwriteBtn = document.getElementById('upload-conflict-overwrite');
const conflictRenameBtn = document.getElementById('upload-conflict-rename');
let droppedFiles    = [];
let _pollTimer      = null;
let conflictDialogState = null;

function getExt(name) { return name.slice(name.lastIndexOf('.')).toLowerCase(); }

function getPreviewKind(file) {
    const ext = getExt(file.name);
    if (['.jpg', '.jpeg', '.png'].includes(ext)) return 'image';
    if (['.mp4', '.webm', '.mov', '.avi', '.mkv'].includes(ext)) return 'video';
    if (ext === '.pdf') return 'pdf';
    return 'file';
}

function previewIcon(kind) {
    if (kind === 'video') {
        return `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="5" width="14" height="14" rx="2"></rect>
                <path d="m17 9 4-2v10l-4-2"></path>
            </svg>`;
    }
    if (kind === 'pdf') {
        return `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                <path d="M14 2v6h6"></path>
                <path d="M8 16h8"></path>
                <path d="M8 12h3"></path>
            </svg>`;
    }
    return `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <circle cx="8.5" cy="8.5" r="1.5"></circle>
            <path d="m21 15-5-5L5 21"></path>
        </svg>`;
}

function filterFiles(files) {
    const valid = [], rejected = [];
    [...files].forEach(f => (ACCEPTED_EXTS.has(getExt(f.name)) ? valid : rejected).push(f));
    return { valid, rejected };
}

function showRejectedBanner(rejected) {
    if (!rejected.length) { rejectedBanner.style.display = 'none'; return; }
    document.getElementById('rejected-banner-title').textContent = MSG_INVALID_FORMAT;
    const list = document.getElementById('rejected-file-list');
    list.innerHTML = rejected.map(f => {
        const ext = getExt(f.name);
        return `<li><span>${f.name}</span><span class="rejected-file-ext">${ext.toUpperCase()}</span></li>`;
    }).join('');
    const acc = document.getElementById('rejected-accepted');
    acc.innerHTML = MSG_ACCEPTED_FORMATS + ' ' + ACCEPTED_LABELS.map(l => `<span class="fmt-badge">${l}</span>`).join('');
    rejectedBanner.style.display = 'block';
}

uploadArea.addEventListener('click', () => fileInput.click());
uploadArea.addEventListener('dragover',  e => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
uploadArea.addEventListener('drop', e => {
    e.preventDefault(); e.stopPropagation();
    uploadArea.classList.remove('dragover');
    const { valid, rejected } = filterFiles(e.dataTransfer.files);
    droppedFiles = [...droppedFiles, ...valid];
    showRejectedBanner(rejected);
    showPreviews(droppedFiles);
});
fileInput.addEventListener('change', () => {
    const { valid, rejected } = filterFiles(fileInput.files);
    droppedFiles = [...droppedFiles, ...valid];
    fileInput.value = '';
    showRejectedBanner(rejected);
    showPreviews(droppedFiles);
});

function showPreviews(files) {
    preview.innerHTML = '';
    [...files].forEach(file => {
        const item = document.createElement('div');
        const kind = getPreviewKind(file);
        const ext = getExt(file.name).replace('.', '').toUpperCase() || 'FILE';
        item.className = 'prev-item';
        item.dataset.kind = kind;
        item.innerHTML = `
            <div class="prev-icon" aria-hidden="true">${previewIcon(kind)}</div>
            <span class="prev-ext">${escapeHtml(ext)}</span>
            <span class="prev-name" title="${escapeHtmlAttr(file.name)}">${escapeHtml(file.name)}</span>
        `;
        if (kind === 'image') {
            const img = document.createElement('img');
            img.alt = '';
            img.addEventListener('load', () => item.classList.add('has-preview'), { once: true });
            img.addEventListener('error', () => item.classList.remove('has-preview'), { once: true });
            img.src = URL.createObjectURL(file);
            item.appendChild(img);
        } else if (kind === 'video') {
            const vid = document.createElement('video');
            vid.muted = true;
            vid.playsInline = true;
            vid.preload = 'metadata';
            vid.addEventListener('loadeddata', () => item.classList.add('has-preview'), { once: true });
            vid.addEventListener('error', () => item.classList.remove('has-preview'), { once: true });
            vid.src = URL.createObjectURL(file);
            item.appendChild(vid);
        }
        preview.appendChild(item);
    });
}

function setUploadingState(active, pct, n) {
    const pctText = (pct || 0) + '%';
    if (active) {
        uploadAnimationStartedAt = performance.now();
        ensureSiteUploadOverlay();
        document.body.classList.add('site-uploading');
        siteUploadOverlay.classList.add('open');
        siteUploadOverlay.setAttribute('aria-hidden', 'false');
        uploadArea.classList.add('uploading');
        uploadArea.setAttribute('aria-busy', 'true');
        overlayTitle.textContent = MSG_UPLOADING;
        overlaySub.textContent = MSG_UPLOADING_FILES.replace('{n}', n);
        overlayPct.textContent = pctText;
        siteOverlayTitle.textContent = MSG_UPLOADING;
        siteOverlaySub.textContent = MSG_UPLOADING_FILES.replace('{n}', n);
        siteOverlayPct.textContent = pctText;
        progressFill.classList.add('active');
    } else {
        if (siteUploadOverlay) {
            siteUploadOverlay.classList.remove('open');
            siteUploadOverlay.setAttribute('aria-hidden', 'true');
        }
        document.body.classList.remove('site-uploading');
        uploadArea.classList.remove('uploading');
        uploadArea.removeAttribute('aria-busy');
        progressFill.classList.remove('active');
    }
}

function ensureSiteUploadOverlay() {
    if (siteUploadOverlay) return;
    siteUploadOverlay = document.createElement('div');
    siteUploadOverlay.className = 'site-upload-overlay';
    siteUploadOverlay.setAttribute('aria-hidden', 'true');
    siteUploadOverlay.innerHTML = `
        <div class="site-upload-panel" role="status" aria-live="polite">
            <div class="upload-spinner-ring">
                <div class="upload-spinner-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                </div>
            </div>
            <div class="site-upload-pct">0%</div>
            <div class="site-upload-title"></div>
            <div class="site-upload-sub"></div>
            <div class="upload-overlay-dots"><span></span><span></span><span></span></div>
        </div>
    `;
    document.body.appendChild(siteUploadOverlay);
    siteOverlayPct = siteUploadOverlay.querySelector('.site-upload-pct');
    siteOverlayTitle = siteUploadOverlay.querySelector('.site-upload-title');
    siteOverlaySub = siteUploadOverlay.querySelector('.site-upload-sub');
}

function waitForUploadAnimation() {
    const elapsed = performance.now() - uploadAnimationStartedAt;
    const remaining = Math.max(0, UPLOAD_ANIMATION_MIN_MS - elapsed);
    return new Promise(resolve => setTimeout(resolve, remaining));
}

const MAX_FILE_SIZE = 150 * 1024 * 1024;
const MAX_BATCH_SIZE = 256 * 1024 * 1024;
function checkSizes(files) {
    const big = [...files].filter(f => f.size > MAX_FILE_SIZE);
    if (big.length) {
        showFlash(MSG_TOO_LARGE.replace('{names}', big.map(f => f.name).join(', ')), 'error');
        return false;
    }
    const total = [...files].reduce((sum, f) => sum + f.size, 0);
    if (total > MAX_BATCH_SIZE) {
        showFlash(MSG_BATCH_TOO_LARGE, 'error');
        return false;
    }
    return true;
}

/* ── Suivi de l'encodage ── */
function startProgressPolling(jobs) {
    encodePanel.style.display = 'block';
    encodeJobs.innerHTML = '';
    const jobMap = {};
    jobs.forEach(j => {
        const wrap  = document.createElement('div'); wrap.className = 'encode-job';
        const label = document.createElement('div'); label.className = 'encode-job-name';
        label.innerHTML = `${j.filename} <span id="pct-${j.id}">0%</span>`;
        const barWrap = document.createElement('div'); barWrap.className = 'encode-bar-wrap';
        const bar     = document.createElement('div'); bar.className = 'encode-bar-fill'; bar.id = `bar-${j.id}`;
        barWrap.appendChild(bar); wrap.appendChild(label); wrap.appendChild(barWrap);
        encodeJobs.appendChild(wrap);
        jobMap[j.id] = j.filename;
    });

    function poll() {
        fetch('/api/queue').then(r => r.json()).then(data => {
            let allDone = true;
            jobs.forEach(j => {
                const uj  = (data.upload_jobs || []).find(x => x.filename === j.filename);
                const bar = document.getElementById(`bar-${j.id}`);
                const pct = document.getElementById(`pct-${j.id}`);
                if (!uj || uj.status === 'processing') {
                    allDone = false;
                    const p = Math.max(0, uj ? (uj.progress || 0) : 0);
                    if (bar) bar.style.width = p + '%';
                    if (pct) pct.textContent = p + '%';
                } else if (uj.status === 'done') {
                    if (bar) { bar.style.width = '100%'; bar.classList.add('done'); }
                    if (pct) pct.textContent = '100%';
                } else if (uj.status === 'error') {
                    if (bar) bar.classList.add('error');
                    if (pct) pct.textContent = MSG_ENCODING_ERROR;
                }
            });
            if (!allDone) {
                _pollTimer = setTimeout(poll, 1500);
            } else {
                document.getElementById('encode-panel-title').textContent = MSG_ENCODING_DONE;
                document.getElementById('btn-go-media').style.display = 'inline-flex';
            }
        }).catch(() => { _pollTimer = setTimeout(poll, 3000); });
    }
    poll();
}

function splitFilename(filename) {
    const dot = filename.lastIndexOf('.');
    if (dot <= 0) return { base: filename, ext: '' };
    return { base: filename.slice(0, dot), ext: filename.slice(dot) };
}

function normalizeConflictEntries(conflicts) {
    const entries = (conflicts || []).map((entry, index) => {
        if (typeof entry === 'string') {
            return { uploadIndex: index, filename: entry };
        }
        return {
            uploadIndex: Number.isInteger(entry?.upload_index) ? entry.upload_index : index,
            filename: String(entry?.filename || ''),
        };
    }).filter(entry => entry.filename);

    const occurrences = new Map();
    return entries.map(entry => {
        const count = (occurrences.get(entry.filename) || 0) + 1;
        occurrences.set(entry.filename, count);
        return { ...entry, occurrence: count };
    });
}

function openConflictDialog(conflicts, message = '') {
    const entries = normalizeConflictEntries(conflicts);
    return new Promise(resolve => {
        conflictDialogState = { resolve, entries };
        conflictTitle.textContent = MSG_NAME_CONFLICT_TITLE;
        conflictHeadText.textContent = MSG_NAME_CONFLICT_TEXT;

        const summary = entries.map(entry => `<strong>${escapeHtml(entry.filename)}</strong>`).join(', ');
        conflictBody.innerHTML = `
            <div class="upload-conflict-summary">${MSG_NAME_CONFLICT_LIST} : ${summary}</div>
            <div class="upload-conflict-error${message ? ' open' : ''}" id="upload-conflict-error">${escapeHtml(message || '')}</div>
            ${entries.map((entry, index) => {
                const { base, ext } = splitFilename(entry.filename);
                const occurrenceBadge = entry.occurrence > 1
                    ? `<span class="upload-conflict-current">${MSG_NAME_OCCURRENCE} ${entry.occurrence}</span>`
                    : '';
                return `
                    <div class="upload-conflict-row">
                        <label for="upload-conflict-input-${index}">
                            <span class="upload-conflict-label-line">
                                <span>${MSG_NAME_INPUT_LABEL}</span>
                                <span style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                                    <span class="upload-conflict-current">${MSG_NAME_CURRENT_LABEL} : ${escapeHtml(entry.filename)}</span>
                                    ${occurrenceBadge}
                                </span>
                            </span>
                        </label>
                        <input
                            id="upload-conflict-input-${index}"
                            type="text"
                            data-upload-index="${entry.uploadIndex}"
                            data-original-name="${escapeHtmlAttr(entry.filename)}"
                            data-original-ext="${escapeHtmlAttr(ext)}"
                            value="${escapeHtmlAttr(base)}"
                            autocomplete="off"
                            spellcheck="false"
                        >
                        <small class="upload-conflict-help">${MSG_NAME_INPUT_HELP} ${escapeHtml(ext)}</small>
                    </div>
                `;
            }).join('')}
        `;

        conflictModal.classList.add('open');
        conflictModal.setAttribute('aria-hidden', 'false');
        const firstInput = conflictBody.querySelector('input');
        if (firstInput) {
            requestAnimationFrame(() => {
                firstInput.focus();
                firstInput.select();
            });
        }
    });
}

function closeConflictDialog(result) {
    if (!conflictDialogState) return;
    const { resolve } = conflictDialogState;
    conflictDialogState = null;
    conflictModal.classList.remove('open');
    conflictModal.setAttribute('aria-hidden', 'true');
    conflictBody.innerHTML = '';
    resolve(result);
}

function setConflictError(message) {
    const box = document.getElementById('upload-conflict-error');
    if (!box) return;
    box.textContent = message;
    box.classList.add('open');
}

function collectRenameMap() {
    const inputs = [...conflictBody.querySelectorAll('input[data-upload-index]')];
    const renameMap = {};
    const targets = new Set();

    for (const input of inputs) {
        const uploadIndex = input.dataset.uploadIndex || '';
        const originalName = input.dataset.originalName || '';
        const originalExt = (input.dataset.originalExt || '').toLowerCase();
        const rawValue = input.value.trim();

        if (!rawValue) {
            input.focus();
            input.select();
            setConflictError(MSG_NAME_REQUIRED);
            return null;
        }

        const hasExt = rawValue.includes('.');
        const proposed = hasExt ? rawValue : `${rawValue}${originalExt}`;
        const proposedExt = getExt(proposed);

        if (proposedExt !== originalExt) {
            input.focus();
            input.select();
            setConflictError(MSG_NAME_EXT_MISMATCH);
            return null;
        }
        if (targets.has(proposed.toLowerCase())) {
            input.focus();
            input.select();
            setConflictError(MSG_NAME_DUPLICATE);
            return null;
        }

        targets.add(proposed.toLowerCase());
        renameMap[uploadIndex] = proposed;
    }

    return renameMap;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeHtmlAttr(value) {
    return escapeHtml(value);
}

conflictCancelBtn.addEventListener('click', () => closeConflictDialog(null));
conflictOverwriteBtn.addEventListener('click', () => closeConflictDialog({ strategy: 'overwrite' }));
conflictRenameBtn.addEventListener('click', () => {
    const renameMap = collectRenameMap();
    if (!renameMap) return;
    closeConflictDialog({ strategy: 'rename_custom', renameMap });
});
document.querySelectorAll('.queue-force-form').forEach(form => {
    form.addEventListener('submit', async event => {
        event.preventDefault();
        const ok = await window.appUI.confirm({
            titleText: QUEUE_FORCE_TITLE,
            messageText: QUEUE_FORCE_CONFIRM,
            note: adminUploadConfig.queueForceImpact || '',
            tone: 'warning',
            confirmLabel: QUEUE_FORCE_TITLE,
        });
        if (ok) form.submit();
    });
});
conflictModal.addEventListener('click', event => {
    if (event.target === conflictModal) closeConflictDialog(null);
});
document.querySelector('.upload-conflict-dialog').addEventListener('click', e => e.stopPropagation());
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        event.preventDefault();
        if (conflictDialogState) closeConflictDialog(null);
        return;
    }
    if (conflictDialogState && event.key === 'Enter' && event.target instanceof HTMLInputElement) {
        event.preventDefault();
        conflictRenameBtn.click();
    }
});

function submitUploadFiles(files, strategy = '', renameMap = null) {
    const fd = new FormData();
    files.forEach(f => fd.append('file', f));
    if (strategy) fd.append('conflict_strategy', strategy);
    if (renameMap) fd.append('rename_map', JSON.stringify(renameMap));
    const xhr = new XMLHttpRequest();
    progressWrap.style.display = 'block'; progressFill.style.width = '0';
    setUploadingState(true, 0, files.length);
    xhr.upload.addEventListener('progress', ev => {
        if (ev.lengthComputable) {
            const pct = Math.round(ev.loaded / ev.total * 100);
            progressFill.style.width = pct + '%';
            overlayPct.textContent = pct + '%';
            if (siteOverlayPct) siteOverlayPct.textContent = pct + '%';
        }
    });
    xhr.addEventListener('load', async () => {
        await waitForUploadAnimation();
        setUploadingState(false);
        progressWrap.style.display = 'none';
        let data = {};
        try {
            data = JSON.parse(xhr.responseText || '{}');
        } catch {
            data = {};
        }
        if (xhr.status === 413) {
            const message = data.error === 'file too large'
                ? MSG_FILE_TOO_LARGE
                : MSG_BATCH_TOO_LARGE;
            showFlash(message, 'error');
            return;
        }
        if (xhr.status === 409 && data.error === 'name conflict') {
            const retryMessage = data.message || '';
            const choice = await openConflictDialog(data.conflicts || [], retryMessage);
            if (!choice) return;
            submitUploadFiles(files, choice.strategy, choice.renameMap || null);
            return;
        }
        if (xhr.status >= 400) {
            const message = data.error === 'unsupported file type'
                ? MSG_UNSUPPORTED_TYPE
                : data.error === 'invalid image file'
                    ? MSG_INVALID_IMAGE
                    : data.error === 'batch too large'
                        ? MSG_BATCH_TOO_LARGE
                    : data.error === 'file too large'
                        ? MSG_FILE_TOO_LARGE
                    : data.error === 'missing rename'
                        ? MSG_NAME_MISSING
                    : data.error === 'extension mismatch'
                        ? MSG_NAME_EXT_MISMATCH
                    : data.error === 'target exists'
                        ? MSG_NAME_EXISTS
                    : (data.error || `${MSG_UPLOAD_FAILED} (HTTP ${xhr.status})`);
            showFlash(message, 'error');
            return;
        }
        if (Array.isArray(data.warnings) && data.warnings.length) {
            window.appUI.showFlashAfterReload(data.warnings.join('\n'), 'warning');
        }
        window.location.href = data.redirect || '/admin/media';
    });
    xhr.addEventListener('error', async () => {
        await waitForUploadAnimation();
        setUploadingState(false);
        progressWrap.style.display = 'none';
        showFlash(MSG_NETWORK_ERROR, 'error');
    });
    xhr.open('POST', '/upload');
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    xhr.setRequestHeader('X-CSRF-Token', window.CSRF_TOKEN);
    xhr.send(fd);
}

document.getElementById('upload-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const files = droppedFiles.length ? droppedFiles : [...fileInput.files];
    if (!files.length) return;
    if (!checkSizes(files)) return;
    submitUploadFiles(files);
});

function showFlash(msg, type) {
    window.appUI.showFlash(msg, type);
}

if (adminUploadConfig.realtimeQueueEnabled) {
async function refreshQueue() {
    try {
        const res = await fetch('/api/queue');
        const data = await res.json();

        const banner = document.getElementById('window-banner');
        const dot = document.getElementById('window-dot');
        const text = document.getElementById('window-text');
        if (banner && dot && text) {
            const h = new Date().getHours();
            const active = h >= 20 || h < 6;
            banner.className = `window-banner ${active ? 'on' : 'off'}`;
            dot.className = `window-dot ${active ? 'on' : 'off'}`;
            if (active) {
                text.textContent = JS_WINDOW_ACTIVE;
            } else {
                const next = h < 20 ? JS_TONIGHT : JS_TOMORROW;
                text.innerHTML = `${JS_WINDOW_INACTIVE} <strong>${next}</strong>`;
            }
        }

        const activeEl = document.getElementById('active-jobs');
        if (activeEl) {
            if ((data.active || []).length) {
                activeEl.innerHTML = data.active.map(j => {
                    const isPending = j.status === 'pending';
                    const pct = (j.progress !== undefined && j.progress >= 0) ? j.progress : null;
                    const progressBar = (!isPending && pct !== null)
                        ? `<div class="job-progress-wrap"><div class="job-progress-fill" style="width:${pct}%"></div></div>`
                        : '';
                    const metaPct = (!isPending && pct !== null) ? ` — ${pct}%` : '';
                    return `<div class="job-card">
                        <div class="job-icon ${j.status}">${isPending ? '⏳' : '⚙️'}</div>
                        <div class="job-info">
                            <div class="job-name">${j.filename}</div>
                            <div class="job-meta">${JS_ADDED_ON} ${j.added.slice(0,16).replace('T',' ')}${metaPct}</div>
                            ${progressBar}
                        </div>
                        <span class="job-status ${j.status}">${isPending ? JS_PENDING : JS_PROCESSING}</span>
                        ${isPending ? `<button class="btn sm danger js-cancel-job" data-job-id="${j.id}">${JS_CANCEL_BTN}</button>` : ''}
                    </div>`;
                }).join('');
            } else {
                activeEl.innerHTML = `<div class="empty-queue">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                    <p>${JS_EMPTY_ACTIVE}</p></div>`;
            }
        }

        const clearRecentBtn = document.getElementById('btn-clear-recent');
        if (clearRecentBtn) {
            clearRecentBtn.style.display = (data.recent || []).length ? 'inline-flex' : 'none';
        }

        const recentEl = document.getElementById('recent-jobs');
        if (recentEl) {
            if ((data.recent || []).length) {
                recentEl.innerHTML = [...data.recent].reverse().map(j => {
                    const isDone = j.status === 'done';
                    const result = isDone
                        ? `<span class="job-result">${j.before} Mo → ${j.after} Mo (÷${j.ratio})</span>`
                        : `<span class="job-result error">${j.message || 'ffmpeg failed'}</span>`;
                    return `<div class="job-card">
                        <div class="job-icon" style="font-size:1.2rem">${isDone ? '✅' : '❌'}</div>
                        <div class="job-info">
                            <div class="job-name">${j.filename}</div>
                            <div class="job-meta">${result} — ${(j.finished||'').slice(0,16).replace('T',' ')}</div>
                        </div>
                        <span class="job-status ${j.status}">${isDone ? JS_DONE : JS_ERROR}</span>
                        <button class="js-cancel-job" data-job-id="${j.id}" style="background:none;border:none;cursor:pointer;color:var(--text-3);font-size:1rem;padding:4px;" title="✕">✕</button>
                    </div>`;
                }).join('');
            } else {
                recentEl.innerHTML = `<div class="empty-queue" style="padding:20px"><p>${JS_EMPTY_RECENT}</p></div>`;
            }
        }

        const badge = document.getElementById('nav-queue-badge');
        if (badge) {
            const n = (data.active || []).length;
            badge.style.display = n ? 'inline' : 'none';
            badge.textContent = n;
        }
    } catch {}
}

async function cancelJob(id) {
    if (!await window.appUI.confirm({
        titleText: JS_CANCEL_BTN,
        messageText: JS_CONFIRM_CANCEL,
        tone: 'warning',
        confirmLabel: cfg.yes || 'Oui',
        cancelLabel: cfg.no || 'Non',
    })) return;
    await fetch(`/queue/cancel/${id}`, {
        method: 'POST',
        headers: { 'X-CSRF-Token': window.CSRF_TOKEN },
    });
    refreshQueue();
}
window.cancelJob = cancelJob;

document.getElementById('btn-clear-recent')?.addEventListener('click', async () => {
    if (!await window.appUI.confirm({
        titleText: cfg.clearRecentTitle || 'Tout effacer',
            messageText: cfg.clearRecentConfirm || 'Remove all recent encodings from the list?',
        tone: 'warning',
        confirmLabel: cfg.clearRecentBtn || 'Effacer',
        cancelLabel: cfg.cancelBtn || 'Annuler',
    })) return;
    await fetch('/queue/clear-recent', {
        method: 'POST',
        headers: { 'X-CSRF-Token': window.CSRF_TOKEN },
    });
    refreshQueue();
});

    refreshQueue();
    setInterval(refreshQueue, 5000);

    document.getElementById('active-jobs')?.addEventListener('click', e => {
        const btn = e.target.closest('.js-cancel-job');
        if (btn) cancelJob(btn.dataset.jobId);
    });
    document.getElementById('recent-jobs')?.addEventListener('click', e => {
        const btn = e.target.closest('.js-cancel-job');
        if (btn) cancelJob(btn.dataset.jobId);
    });
}
