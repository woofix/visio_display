const adminMediaConfigEl = document.getElementById('admin-media-config');
const adminMediaConfig = adminMediaConfigEl ? JSON.parse(adminMediaConfigEl.textContent || '{}') : {};
const CURRENT_SCREEN          = adminMediaConfig.currentScreen || '';
const JS_CONFIRM_COMPRESS     = adminMediaConfig.confirmCompress || '';
const JS_CONFIRM_DELETE       = adminMediaConfig.confirmDelete || '';
const JS_COMPRESS_ADDING      = adminMediaConfig.compressAdding || '';
const JS_COMPRESS_WAITING     = adminMediaConfig.compressWaiting || '';
const JS_COMPRESS_ERR_PREFIX  = adminMediaConfig.compressErrorPrefix || '';
const JS_COMPRESS_ERR_NET     = adminMediaConfig.compressErrorNetwork || '';
const JS_FLASH_ADDED_QUEUE    = adminMediaConfig.flashAddedQueue || '';
const JS_SCHEDULE_SAVED       = adminMediaConfig.scheduleSaved || '';
const JS_SCHEDULE_CLEARED     = adminMediaConfig.scheduleCleared || '';
const JS_SAVE_ERROR           = adminMediaConfig.saveError || '';
const JS_DISABLED_LABEL       = adminMediaConfig.disabledLabel || '';
const JS_ACTIVE_SCHEDULE      = adminMediaConfig.activeSchedule || '';
const JS_ACTION_ENABLE        = adminMediaConfig.actionEnable || '';
const JS_ACTION_DISABLE       = adminMediaConfig.actionDisable || '';
const JS_FORCE_CONFIRM        = adminMediaConfig.forceConfirm || '';
const JS_FORCE_LAUNCHING      = adminMediaConfig.forceLaunching || '';
const JS_FORCE_RUNNING        = adminMediaConfig.forceRunning || '';
const JS_ACTION_FORCE         = adminMediaConfig.actionForce || '';
const JS_SCREEN_ADDED         = adminMediaConfig.screenAdded || '';
const JS_SCREEN_REMOVED       = adminMediaConfig.screenRemoved || '';
const JS_SCREEN_REMOVE_CONFIRM = adminMediaConfig.screenRemoveConfirm || '';
const JS_ADD_TO_SCREEN        = adminMediaConfig.addToScreen || '';
const SCREEN_DELETE_CONFIRM   = adminMediaConfig.screenDeleteConfirm || '';
const JS_GROUPS_SAVED         = adminMediaConfig.groupsSaved || '';
const JS_GROUP_ENABLED        = adminMediaConfig.groupEnabled || '';
const JS_GROUP_DISABLED       = adminMediaConfig.groupDisabled || '';
const JS_GROUP_ENABLE         = adminMediaConfig.groupEnable || '';
const JS_GROUP_DISABLE        = adminMediaConfig.groupDisable || '';
const JS_GROUP_POOL_SAVED     = adminMediaConfig.groupPoolSaved || '';
const JS_GROUP_POOL_CLEARED   = adminMediaConfig.groupPoolCleared || '';
const JS_GROUP_SCREENS_SAVED  = adminMediaConfig.groupScreensSaved || '';
const ALL_SCREENS             = adminMediaConfig.screens || [];
const JS_ACTION_COMPRESS      = adminMediaConfig.actionCompress || '';
const SCREEN_TOKEN_PARAM      = adminMediaConfig.screenTokenParam || 'screen_token';
const DISPLAY_API_TOKEN       = adminMediaConfig.displayApiToken || '';

/* ── Screen preview modal ── */
(function() {
    const btn = document.getElementById('btn-preview-screen');
    if (!btn) return;
    const overlay = document.getElementById('screen-preview-overlay');
    const iframe  = document.getElementById('screen-preview-iframe');
    const closeBtn = document.getElementById('screen-preview-close-btn');
    const screenToken = DISPLAY_API_TOKEN;

    function open() {
        const params = new URLSearchParams();
        if (CURRENT_SCREEN) params.set('screen', CURRENT_SCREEN);
        params.set(SCREEN_TOKEN_PARAM, screenToken);
        iframe.src = '/?' + params.toString();
        overlay.classList.add('open');
    }
    function close() {
        overlay.classList.remove('open');
        iframe.src = '';
    }

    btn.addEventListener('click', open);
    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
})();

/* ── Sort active on top, disabled at bottom ── */
function sortMediaCards() {
    const grid = document.getElementById('file-grid');
    const cards = [...grid.querySelectorAll('.file-card')];
    const active   = cards.filter(c => c.dataset.disabled === 'false');
    const disabled = cards.filter(c => c.dataset.disabled === 'true');
    grid.querySelector('.disabled-sep')?.remove();
    active.forEach(c => grid.appendChild(c));
    if (disabled.length) {
        const sep = document.createElement('div');
        sep.className = 'disabled-sep';
        sep.innerHTML = `<div class="disabled-sep-line"></div><span class="disabled-sep-label">${JS_DISABLED_LABEL.replace('{n}', disabled.length)}</span><div class="disabled-sep-line"></div>`;
        grid.appendChild(sep);
        disabled.forEach(c => grid.appendChild(c));
    }
}
sortMediaCards();

/* ── URL param filter on load ── */
(function() {
    const p = new URLSearchParams(window.location.search);
    const f = p.get('filter'); if (f) document.getElementById('media-filter').value = f;
    const q = p.get('q');      if (q) document.getElementById('media-search').value = q;
    applyFilter();
})();

/* ── Search + filter ── */
function applyFilter() {
    const q   = document.getElementById('media-search').value.toLowerCase().trim();
    const fil = document.getElementById('media-filter').value;
    let visible = 0;
    document.querySelectorAll('.file-card').forEach(card => {
        const name     = card.dataset.file.toLowerCase();
        const type     = card.dataset.type;
        const disabled = card.dataset.disabled === 'true';
        let show = name.includes(q);
        if (show && fil === 'active')   show = !disabled;
        if (show && fil === 'disabled') show = disabled;
        if (show && fil === 'image')    show = type === 'image';
        if (show && fil === 'video')    show = type === 'video';
        card.style.display = show ? '' : 'none';
        if (show) visible++;
    });
    document.getElementById('media-empty').style.display = visible === 0 ? 'block' : 'none';
}
document.getElementById('media-search').addEventListener('input', applyFilter);
document.getElementById('media-filter').addEventListener('change', applyFilter);

function refreshCardDisabledState(card) {
    const isDisabled = card.dataset.manuallyDisabled === 'true' || card.dataset.groupDisabled === 'true';
    card.dataset.disabled = isDisabled ? 'true' : 'false';
    card.classList.toggle('disabled', isDisabled);
    card.classList.toggle('group-disabled', card.dataset.groupDisabled === 'true' && card.dataset.manuallyDisabled !== 'true');
    const preview = card.querySelector('.thumb, .thumb-video');
    if (preview) {
        preview.dataset.previewDisabled = isDisabled ? 'true' : 'false';
        preview.style.pointerEvents = isDisabled ? 'none' : '';
    }
}

/* ── Grid / list view toggle ── */
(function() {
    const grid = document.getElementById('file-grid');
    const saved = localStorage.getItem('mediaView') || 'grid';
    function setView(v) {
        grid.classList.toggle('list-view', v === 'list');
        const unassigned = document.getElementById('unassigned-grid');
        if (unassigned) unassigned.classList.toggle('list-view', v === 'list');
        document.getElementById('btn-grid').classList.toggle('active', v !== 'list');
        document.getElementById('btn-list').classList.toggle('active', v === 'list');
        localStorage.setItem('mediaView', v);
    }
    setView(saved);
    document.getElementById('btn-grid').addEventListener('click', () => setView('grid'));
    document.getElementById('btn-list').addEventListener('click', () => setView('list'));
})();

/* ── Enable / disable toggle ── */
document.querySelectorAll('.btn-toggle').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        btn.closest('.dropdown-menu')?.classList.remove('open');
        const file = btn.dataset.file;
        const res  = await fetch(`/toggle/${encodeURIComponent(file)}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ screen: CURRENT_SCREEN })
        });
        const data = await res.json();
        const card = btn.closest('.file-card');
        if (data.state === 'disabled') {
            card.dataset.manuallyDisabled = 'true';
            btn.classList.replace('success-item', 'warning-item');
            btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg> ${JS_ACTION_ENABLE}`;
        } else {
            card.dataset.manuallyDisabled = 'false';
            btn.classList.replace('warning-item', 'success-item');
            btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg> ${JS_ACTION_DISABLE}`;
        }
        refreshCardDisabledState(card);
        sortMediaCards();
    });
});

document.querySelectorAll('.btn-save-groups').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        const input = btn.closest('.group-editor')?.querySelector('.group-input');
        if (!input) return;
        const file = btn.dataset.file;
        const groups = input.value.split(',').map(v => v.trim()).filter(Boolean);
        btn.disabled = true;
        try {
            const res = await fetch(`/set_groups/${encodeURIComponent(file)}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ groups })
            });
            const data = await res.json();
            if (data.ok) {
                window.appUI.showFlashAfterReload(JS_GROUPS_SAVED.replace('{file}', file), 'success');
                window.location.reload();
            } else {
                showFlash(data.error || JS_SAVE_ERROR, 'error');
                btn.disabled = false;
            }
        } catch {
            showFlash(JS_COMPRESS_ERR_NET, 'error');
            btn.disabled = false;
        }
    });
});

document.querySelectorAll('.group-input').forEach(input => {
    input.addEventListener('keydown', e => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        input.closest('.group-editor')?.querySelector('.btn-save-groups')?.click();
    });
});

document.querySelectorAll('.btn-toggle-group').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        const group = btn.dataset.group;
        btn.disabled = true;
        try {
            const res = await fetch(`/toggle_group/${encodeURIComponent(group)}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ screen: CURRENT_SCREEN })
            });
            const data = await res.json();
            if (data.state === 'disabled') {
                window.appUI.showFlashAfterReload(JS_GROUP_DISABLED.replace('{group}', group), 'success');
            } else if (data.state === 'enabled') {
                window.appUI.showFlashAfterReload(JS_GROUP_ENABLED.replace('{group}', group), 'success');
            } else {
                showFlash(data.error || JS_SAVE_ERROR, 'error');
                btn.disabled = false;
                return;
            }
            window.location.reload();
        } catch {
            showFlash(JS_COMPRESS_ERR_NET, 'error');
            btn.disabled = false;
        }
    });
});

/* ── Group pool size ── */
document.querySelectorAll('.group-pool-input').forEach(input => {
    let timer;
    const save = async () => {
        const group = input.dataset.group;
        const poolSize = parseInt(input.value) || 0;
        try {
            const res = await fetch(`/set_group_pool/${encodeURIComponent(group)}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ pool_size: poolSize })
            });
            const data = await res.json();
            if (data.ok) {
                if (poolSize > 0) {
                    showFlash(JS_GROUP_POOL_SAVED.replace('{group}', group).replace('{size}', poolSize), 'success');
                } else {
                    showFlash(JS_GROUP_POOL_CLEARED.replace('{group}', group), 'success');
                }
            } else {
                showFlash(data.error || JS_SAVE_ERROR, 'error');
            }
        } catch {
            showFlash(JS_SAVE_ERROR, 'error');
        }
    };
    input.addEventListener('change', () => { clearTimeout(timer); timer = setTimeout(save, 400); });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') { clearTimeout(timer); save(); } });
});

/* ── Group screens toggle (opens/closes the picker) ── */
document.querySelectorAll('.btn-group-screens-toggle').forEach(btn => {
    btn.addEventListener('click', e => {
        e.stopPropagation();
        const chip = document.querySelector(`.group-chip[data-group-chip="${btn.dataset.group}"]`);
        if (chip) chip.classList.toggle('screens-open');
    });
});

/* ── Group-to-screen link ── */
document.querySelectorAll('.btn-group-screen-link').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        const group  = btn.dataset.group;
        const screen = btn.dataset.screen;
        const chip   = document.querySelector(`.group-chip[data-group-chip="${group}"]`);
        const current = JSON.parse(chip.dataset.screens || '[]');
        const next    = current.includes(screen)
            ? current.filter(s => s !== screen)
            : [...current, screen];
        btn.disabled = true;
        try {
            const res  = await fetch(`/set_group_screens/${encodeURIComponent(group)}`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ screens: next })
            });
            const data = await res.json();
            if (data.ok) {
                chip.dataset.screens = JSON.stringify(data.screens);
                btn.classList.toggle('linked', data.screens.includes(screen));
                chip.classList.toggle('screens-linked', data.screens.length > 0);
                const countEl = chip.querySelector('.group-screens-count');
                const toggleBtn = chip.querySelector('.btn-group-screens-toggle');
                if (data.screens.length > 0) {
                    if (countEl) { countEl.textContent = data.screens.length; }
                    else if (toggleBtn) {
                        const span = document.createElement('span');
                        span.className = 'group-screens-count';
                        span.textContent = data.screens.length;
                        toggleBtn.appendChild(span);
                    }
                } else {
                    countEl?.remove();
                }
                const hint = chip.querySelector('.group-screens-hint');
                if (hint) hint.style.display = data.screens.length ? 'none' : '';
                showFlash(JS_GROUP_SCREENS_SAVED.replace('{group}', group), 'success');
            } else {
                showFlash(data.error || JS_SAVE_ERROR, 'error');
            }
        } catch {
            showFlash(JS_SAVE_ERROR, 'error');
        }
        btn.disabled = false;
    });
});

/* ── Duration auto-save ── */
document.querySelectorAll('.duration-input').forEach(input => {
    let timer;
    input.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => fetch(`/set_duration/${encodeURIComponent(input.dataset.file)}`, {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ duration: parseInt(input.value), screen: CURRENT_SCREEN })
        }), 600);
    });
});

/* ── Compression ── */
document.querySelectorAll('.btn-compress').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        btn.closest('.dropdown-menu')?.classList.remove('open');
        const file = btn.dataset.file;
        if (!await window.appUI.confirm({
            titleText: JS_ACTION_COMPRESS,
            messageText: JS_CONFIRM_COMPRESS.replace('{file}', file),
            tone: 'warning',
            confirmLabel: JS_ACTION_COMPRESS,
        })) return;
        btn.disabled = true; btn.textContent = JS_COMPRESS_ADDING;
        try {
            const res  = await fetch(`/compress/${encodeURIComponent(file)}`, { method:'POST' });
            const data = await res.json();
            if (data.ok) { btn.textContent = JS_COMPRESS_WAITING; showFlash(JS_FLASH_ADDED_QUEUE.replace('{file}', file), 'success'); }
            else { showFlash(JS_COMPRESS_ERR_PREFIX + data.error, 'error'); btn.disabled = false; btn.textContent = '🗜 ' + JS_ACTION_COMPRESS; }
        } catch { showFlash(JS_COMPRESS_ERR_NET, 'error'); btn.disabled = false; btn.textContent = '🗜 ' + JS_ACTION_COMPRESS; }
    });
});

/* ── Force encode (superadmin) ── */
document.querySelectorAll('.btn-force-encode').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        btn.closest('.dropdown-menu')?.classList.remove('open');
        const file = btn.dataset.file;
        if (!await window.appUI.confirm({
            titleText: JS_ACTION_FORCE,
            messageText: JS_FORCE_CONFIRM.replace('{file}', file),
            tone: 'warning',
            confirmLabel: JS_ACTION_FORCE,
        })) return;
        btn.disabled = true;
        btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${JS_FORCE_LAUNCHING}`;
        try {
            const res  = await fetch(`/admin/compress/${encodeURIComponent(file)}/force`, { method: 'POST' });
            const data = await res.json();
            if (data.ok) {
                btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> ${JS_FORCE_RUNNING}`;
                showFlash(JS_FLASH_ADDED_QUEUE.replace('{file}', file), 'success');
            } else {
                showFlash(JS_COMPRESS_ERR_PREFIX + data.error, 'error');
                btn.disabled = false;
                btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> ${JS_ACTION_FORCE}`;
            }
        } catch {
            showFlash(JS_COMPRESS_ERR_NET, 'error');
            btn.disabled = false;
            btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg> ${JS_ACTION_FORCE}`;
        }
    });
});

/* ── Delete ── */
document.querySelectorAll('.btn-delete').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        if (!await window.appUI.confirm({
            titleText: 'Supprimer le média',
            messageText: JS_CONFIRM_DELETE.replace('{file}', btn.dataset.file),
            tone: 'error',
            confirmLabel: 'Supprimer',
        })) return;
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = btn.dataset.action;

        const csrf = document.createElement('input');
        csrf.type = 'hidden';
        csrf.name = '_csrf_token';
        csrf.value = window.CSRF_TOKEN;
        form.appendChild(csrf);

        document.body.appendChild(form);
        form.submit();
    });
});

/* ── Stacking dropdown z-index ── */
new MutationObserver(() => {
    document.querySelectorAll('.file-card').forEach(card => {
        card.classList.toggle('has-dropdown-open', !!card.querySelector('.dropdown-menu.open'));
    });
}).observe(document.getElementById('file-grid'), { subtree:true, attributes:true, attributeFilter:['class'] });

/* ── Flash ── */
function showFlash(msg, type) {
    window.appUI.showFlash(msg, type);
}

/* ── Schedule modal ── */
let _scheduleFile = null;

function openScheduleModal(file, schedData) {
    _scheduleFile = file;
    document.getElementById('modal-filename').textContent = file;

    const s = schedData || {};
    const hasTime = !!(s.time_start || s.time_end);
    const hasDate = !!(s.date_start || s.date_end);

    document.getElementById('chk-time').checked = hasTime;
    document.getElementById('time-start').value   = s.time_start || '';
    document.getElementById('time-end').value     = s.time_end   || '';
    document.getElementById('time-start').disabled = !hasTime;
    document.getElementById('time-end').disabled   = !hasTime;

    document.getElementById('chk-date').checked = hasDate;
    document.getElementById('date-start').value   = s.date_start || '';
    document.getElementById('date-end').value     = s.date_end   || '';
    document.getElementById('date-start').disabled = !hasDate;
    document.getElementById('date-end').disabled   = !hasDate;

    const info = document.getElementById('modal-info');
    if (hasTime || hasDate) {
        const parts = [];
        if (hasTime) parts.push(`${s.time_start || '00:00'} – ${s.time_end || '23:59'}`);
        if (hasDate) parts.push(`${s.date_start || '…'} → ${s.date_end || '…'}`);
        info.textContent = JS_ACTIVE_SCHEDULE + parts.join(' · ');
        info.classList.add('visible');
    } else {
        info.classList.remove('visible');
    }

    document.getElementById('schedule-modal').classList.add('open');
}

document.getElementById('chk-time').addEventListener('change', e => {
    document.getElementById('time-start').disabled = !e.target.checked;
    document.getElementById('time-end').disabled   = !e.target.checked;
});
document.getElementById('chk-date').addEventListener('change', e => {
    document.getElementById('date-start').disabled = !e.target.checked;
    document.getElementById('date-end').disabled   = !e.target.checked;
});

async function saveSchedule(payload) {
    const res  = await fetch(`/schedule/${encodeURIComponent(_scheduleFile)}`, {
        method: 'POST', headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': window.CSRF_TOKEN,
        },
        body: JSON.stringify({ ...payload, screen: CURRENT_SCREEN })
    });
    const data = await res.json();
    if (data.ok) {
        const card = document.querySelector(`.file-card[data-file="${CSS.escape(_scheduleFile)}"]`);
        const isEmpty = !payload.time_start && !payload.time_end && !payload.date_start && !payload.date_end;
        if (card) {
            card.classList.toggle('scheduled', !isEmpty);
            card.dataset.schedule = JSON.stringify(isEmpty ? {} : payload);
        }
        showFlash(isEmpty
            ? JS_SCHEDULE_CLEARED.replace('{file}', _scheduleFile)
            : JS_SCHEDULE_SAVED.replace('{file}', _scheduleFile), 'success');
    } else {
        showFlash(data.error || JS_SAVE_ERROR, 'error');
    }
    document.getElementById('schedule-modal').classList.remove('open');
}

document.getElementById('modal-save-btn').addEventListener('click', () => {
    const payload = {};
    if (document.getElementById('chk-time').checked) {
        payload.time_start = document.getElementById('time-start').value;
        payload.time_end   = document.getElementById('time-end').value;
    }
    if (document.getElementById('chk-date').checked) {
        payload.date_start = document.getElementById('date-start').value;
        payload.date_end   = document.getElementById('date-end').value;
    }
    saveSchedule(payload);
});

document.getElementById('modal-clear-btn').addEventListener('click', () => {
    saveSchedule({});
});

document.getElementById('modal-close-btn').addEventListener('click', () => {
    document.getElementById('schedule-modal').classList.remove('open');
});
document.getElementById('schedule-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.remove('open');
});

document.querySelectorAll('.btn-schedule').forEach(btn => {
    btn.addEventListener('click', e => {
        e.stopPropagation();
        btn.closest('.dropdown-menu')?.classList.remove('open');
        const card  = btn.closest('.file-card');
        const sched = JSON.parse(card.dataset.schedule || '{}');
        openScheduleModal(btn.dataset.file, sched);
    });
});

/* ── Screen assign / remove ── */
async function screenAssign(file, action) {
    const res  = await fetch(`/screen_assign/${encodeURIComponent(file)}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ screen: CURRENT_SCREEN, action })
    });
    return await res.json();
}

document.querySelectorAll('.btn-add-to-screen').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        btn.disabled = true; btn.textContent = '…';
        const data = await screenAssign(btn.dataset.file, 'add');
        if (data.ok) {
            window.location.reload();
        } else {
            showFlash(data.error || JS_COMPRESS_ERR_NET, 'error');
            btn.disabled = false; btn.textContent = JS_ADD_TO_SCREEN;
        }
    });
});

document.querySelectorAll('.btn-remove-from-screen').forEach(btn => {
    btn.addEventListener('click', async e => {
        e.stopPropagation();
        btn.closest('.dropdown-menu')?.classList.remove('open');
        const file = btn.dataset.file;
        if (!await window.appUI.confirm({
            titleText: 'Retirer de l’écran',
            messageText: JS_SCREEN_REMOVE_CONFIRM.replace('{file}', file).replace('{screen}', CURRENT_SCREEN),
            tone: 'warning',
            confirmLabel: 'Retirer',
        })) return;
        const data = await screenAssign(file, 'remove');
        if (data.ok) {
            showFlash(JS_SCREEN_REMOVED.replace('{file}', file).replace('{screen}', CURRENT_SCREEN), 'success');
            window.location.reload();
        } else {
            showFlash(data.error || JS_COMPRESS_ERR_NET, 'error');
        }
    });
});


/* ── Drag & drop reorder ── */
(function() {
    const grid = document.getElementById('file-grid');
    let dragSrc = null;

    function isDragEnabled() {
        const q = document.getElementById('media-search').value.trim();
        const f = document.getElementById('media-filter').value;
        return !q && f === 'all';
    }

    function updateDraggable() {
        const enabled = isDragEnabled();
        grid.querySelectorAll('.file-card').forEach(card => {
            card.draggable = enabled;
        });
        grid.querySelectorAll('.thumb, .thumb-video').forEach(el => {
            el.draggable = false;
        });
    }

    grid.addEventListener('dragstart', e => {
        if (e.target.matches('.thumb, .thumb-video')) {
            e.preventDefault();
            return;
        }
        const card = e.target.closest('.file-card');
        if (!card) return;
        dragSrc = card;
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });

    grid.addEventListener('dragend', () => {
        if (dragSrc) dragSrc.classList.remove('dragging');
        grid.querySelectorAll('.file-card.drag-over').forEach(c => c.classList.remove('drag-over'));
        dragSrc = null;
    });

    grid.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const card = e.target.closest('.file-card');
        grid.querySelectorAll('.file-card.drag-over').forEach(c => c.classList.remove('drag-over'));
        if (card && card !== dragSrc) card.classList.add('drag-over');
    });

    grid.addEventListener('dragleave', e => {
        if (!grid.contains(e.relatedTarget))
            grid.querySelectorAll('.file-card.drag-over').forEach(c => c.classList.remove('drag-over'));
    });

    grid.addEventListener('drop', e => {
        e.preventDefault();
        const target = e.target.closest('.file-card');
        if (!target || target === dragSrc) return;
        target.classList.remove('drag-over');

        const rect = target.getBoundingClientRect();
        const isListView = grid.classList.contains('list-view');
        const insertBefore = isListView
            ? e.clientY < rect.top + rect.height / 2
            : e.clientX < rect.left + rect.width / 2;

        grid.insertBefore(dragSrc, insertBefore ? target : target.nextSibling);
        saveOrder();
    });

    async function saveOrder() {
        const order = [...grid.querySelectorAll('.file-card[data-file]')].map(c => c.dataset.file);
        await fetch('/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order, screen: CURRENT_SCREEN })
        });
    }

    document.getElementById('media-search').addEventListener('input', updateDraggable);
    document.getElementById('media-filter').addEventListener('change', updateDraggable);
    updateDraggable();
})();
