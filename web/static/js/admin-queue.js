const adminQueueConfigEl = document.getElementById('admin-queue-config');
const adminQueueConfig = adminQueueConfigEl ? JSON.parse(adminQueueConfigEl.textContent || '{}') : {};
const JS_WINDOW_ACTIVE   = adminQueueConfig.windowActive || '';
const JS_WINDOW_INACTIVE = adminQueueConfig.windowInactive || '';
const JS_TONIGHT         = adminQueueConfig.tonight || '';
const JS_TOMORROW        = adminQueueConfig.tomorrow || '';
const JS_PENDING         = adminQueueConfig.pending || '';
const JS_PROCESSING      = adminQueueConfig.processing || '';
const JS_DONE            = adminQueueConfig.done || '';
const JS_ERROR           = adminQueueConfig.error || '';
const JS_ADDED_ON        = adminQueueConfig.addedOn || '';
const JS_CANCEL_BTN      = adminQueueConfig.cancelBtn || '';
const JS_EMPTY_ACTIVE    = adminQueueConfig.emptyActive || '';
const JS_EMPTY_RECENT    = adminQueueConfig.emptyRecent || '';
const JS_CONFIRM_CANCEL  = adminQueueConfig.confirmCancel || '';

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function escapeHtmlAttr(value) {
    return escapeHtml(value);
}

const queueForceModal = document.getElementById('queue-force-modal');
const queueForceCancelBtn = document.getElementById('queue-force-cancel');
const queueForceConfirmBtn = document.getElementById('queue-force-confirm');
let queueForceFormState = null;

function openQueueForceDialog(form) {
    queueForceFormState = form;
    queueForceModal.classList.add('open');
    queueForceModal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => queueForceConfirmBtn.focus());
}

function closeQueueForceDialog() {
    queueForceModal.classList.remove('open');
    queueForceModal.setAttribute('aria-hidden', 'true');
    queueForceFormState = null;
}

document.querySelectorAll('.queue-force-form').forEach(form => {
    form.addEventListener('submit', event => {
        event.preventDefault();
        openQueueForceDialog(form);
    });
});
queueForceCancelBtn.addEventListener('click', closeQueueForceDialog);
queueForceConfirmBtn.addEventListener('click', () => {
    const form = queueForceFormState;
    closeQueueForceDialog();
    if (form) form.submit();
});
queueForceModal.addEventListener('click', event => {
    if (event.target === queueForceModal) closeQueueForceDialog();
});
document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && queueForceFormState) {
        event.preventDefault();
        closeQueueForceDialog();
    }
});

async function refreshQueue() {
    try {
        const res  = await fetch('/api/queue');
        const data = await res.json();

        /* Window status banner */
        const banner = document.getElementById('window-banner');
        const dot    = document.getElementById('window-dot');
        const text   = document.getElementById('window-text');
        const h      = new Date().getHours();
        const active = h >= 20 || h < 6;
        banner.className = `window-banner ${active ? 'on' : 'off'}`;
        dot.className    = `window-dot ${active ? 'on' : 'off'}`;
        if (active) {
            text.textContent = JS_WINDOW_ACTIVE;
        } else {
            const next = h < 20 ? JS_TONIGHT : JS_TOMORROW;
            text.innerHTML = `${JS_WINDOW_INACTIVE} <strong>${next}</strong>`;
        }

        /* Active jobs */
        const activeEl = document.getElementById('active-jobs');
        if ((data.active || []).length) {
            activeEl.innerHTML = data.active.map(j => {
                const isPending = j.status === 'pending';
                const pct = (j.progress !== undefined && j.progress >= 0) ? j.progress : null;
                const safePct = pct === null ? null : Math.max(0, Math.min(100, Number(pct) || 0));
                const safeStatus = escapeHtmlAttr(j.status || '');
                const safeId = escapeHtmlAttr(j.id || '');
                const progressBar = (!isPending && pct !== null)
                    ? `<div class="job-progress-wrap"><div class="job-progress-fill" style="width:${safePct}%"></div></div>`
                    : '';
                const metaPct = (!isPending && pct !== null) ? ` — ${safePct}%` : '';
                return `<div class="job-card">
                    <div class="job-icon ${safeStatus}">${isPending ? '⏳' : '⚙️'}</div>
                    <div class="job-info">
                        <div class="job-name">${escapeHtml(j.filename || '')}</div>
                        <div class="job-meta">${escapeHtml(JS_ADDED_ON)} ${escapeHtml((j.added || '').slice(0,16).replace('T',' '))}${metaPct}</div>
                        ${progressBar}
                    </div>
                    <span class="job-status ${safeStatus}">${isPending ? escapeHtml(JS_PENDING) : escapeHtml(JS_PROCESSING)}</span>
                    ${isPending ? `<button class="btn sm danger" onclick="cancelJob('${safeId}')">${escapeHtml(JS_CANCEL_BTN)}</button>` : ''}
                </div>`;
            }).join('');
        } else {
            activeEl.innerHTML = `<div class="empty-queue">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3"><circle cx="12" cy="12" r="10"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                <p>${JS_EMPTY_ACTIVE}</p></div>`;
        }

        /* Recent jobs */
        const recentEl = document.getElementById('recent-jobs');
        if ((data.recent || []).length) {
            recentEl.innerHTML = [...data.recent].reverse().map(j => {
                const isDone = j.status === 'done';
                const safeStatus = escapeHtmlAttr(j.status || '');
                const safeId = escapeHtmlAttr(j.id || '');
                const hasCompressionStats = j.before !== undefined && j.after !== undefined && j.ratio !== undefined;
                const result = isDone && hasCompressionStats
                    ? `<span class="job-result">${escapeHtml(j.before)} Mo → ${escapeHtml(j.after)} Mo (÷${escapeHtml(j.ratio)})</span>`
                    : isDone
                        ? `<span class="job-result">${escapeHtml(j.message || JS_DONE)}</span>`
                    : `<span class="job-result error">${escapeHtml(j.message || 'ffmpeg failed')}</span>`;
                return `<div class="job-card">
                    <div class="job-icon result">${isDone ? '✅' : '❌'}</div>
                    <div class="job-info">
                        <div class="job-name">${escapeHtml(j.filename || '')}</div>
                        <div class="job-meta">${result} — ${escapeHtml((j.finished||'').slice(0,16).replace('T',' '))}</div>
                    </div>
                    <span class="job-status ${safeStatus}">${isDone ? escapeHtml(JS_DONE) : escapeHtml(JS_ERROR)}</span>
                    <button onclick="cancelJob('${safeId}')" class="job-dismiss" title="✕">✕</button>
                </div>`;
            }).join('');
        } else {
            recentEl.innerHTML = `<div class="empty-queue compact"><p>${JS_EMPTY_RECENT}</p></div>`;
        }

        /* Sidebar badge */
        const badge = document.getElementById('nav-queue-badge');
        if (badge) {
            const n = (data.active||[]).length;
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
        confirmLabel: 'OK',
    })) return;
    await fetch(`/queue/cancel/${id}`, { method: 'POST' });
    refreshQueue();
}

refreshQueue();
setInterval(refreshQueue, 15000);
