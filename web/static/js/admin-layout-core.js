/* ── Sidebar subnav ── */
(function() {
    const sidebar = document.getElementById('sidebar');
    const mobileToggle = document.getElementById('mobile-nav-toggle');
    const mobileBackdrop = document.getElementById('mobile-sidebar-backdrop');
    function setSidebarOpen(open) {
        if (!sidebar || !mobileToggle || !mobileBackdrop) return;
        sidebar.classList.toggle('mobile-open', open);
        mobileBackdrop.classList.toggle('open', open);
        document.body.classList.toggle('sidebar-open', open);
        mobileToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function recalcSubnavHeight(el) {
        if (el && el.classList.contains('open')) {
            el.style.setProperty('--subnav-height', el.scrollHeight + 'px');
        }
    }

    document.querySelectorAll('[data-nav-toggle]').forEach(toggle => {
        const targetId = toggle.getAttribute('data-nav-toggle');
        const sub = targetId ? document.getElementById(targetId) : null;
        if (!sub) return;
        if (sub.classList.contains('open')) {
            sub.style.setProperty('--subnav-height', sub.scrollHeight + 'px');
        }
        toggle.addEventListener('click', () => {
            const isOpen = toggle.classList.toggle('open');
            sub.classList.toggle('open', isOpen);
            sub.style.setProperty('--subnav-height', isOpen ? sub.scrollHeight + 'px' : '0px');
            // Recalcule la hauteur du subnav parent si imbriqué
            const parentSub = toggle.closest('.nav-subnav');
            if (parentSub) requestAnimationFrame(() => recalcSubnavHeight(parentSub));
        });
    });

    if (mobileToggle && sidebar && mobileBackdrop) {
        mobileToggle.addEventListener('click', () => {
            setSidebarOpen(!sidebar.classList.contains('mobile-open'));
        });
        mobileBackdrop.addEventListener('click', () => setSidebarOpen(false));
        window.addEventListener('resize', () => {
            if (window.innerWidth > 640) setSidebarOpen(false);
        });
        document.querySelectorAll('.sidebar a, .sidebar button[type="submit"]').forEach(el => {
            el.addEventListener('click', () => {
                if (window.innerWidth <= 640) setSidebarOpen(false);
            });
        });
    }

    window.__closeMobileSidebar = () => setSidebarOpen(false);

})();

/* ── Dropdowns ── */
(function() {
    function syncDropdownCard(menu) {
        const card = menu?.__dropdownCard || menu?.closest('.file-card');
        if (card) card.classList.toggle('has-dropdown-open', menu.classList.contains('open'));
    }

    function resetFloatingMenu(menu) {
        menu.classList.remove('is-floating');
        menu.style.top = '';
        menu.style.left = '';
        menu.style.right = '';
        menu.style.bottom = '';
        menu.style.visibility = '';
        if (menu.__dropdownParent && menu.parentNode !== menu.__dropdownParent) {
            menu.__dropdownParent.insertBefore(menu, menu.__dropdownNext || null);
        }
    }

    function closeAll() {
        document.querySelectorAll('.dropdown-menu.open').forEach(menu => {
            menu.classList.remove('open');
            resetFloatingMenu(menu);
            syncDropdownCard(menu);
        });
    }

    function positionFloatingMenu(btn, menu) {
        const gap = 6;
        const margin = 10;
        if (!menu.__dropdownParent) {
            menu.__dropdownParent = menu.parentNode;
            menu.__dropdownNext = menu.nextSibling;
            menu.__dropdownCard = menu.closest('.file-card');
        }
        document.body.appendChild(menu);

        const btnRect = btn.getBoundingClientRect();
        menu.classList.add('is-floating');
        menu.style.right = 'auto';
        menu.style.bottom = 'auto';
        menu.style.left = '0px';
        menu.style.top = '0px';
        menu.style.visibility = 'hidden';

        const menuRect = menu.getBoundingClientRect();
        const openDown = (
            window.innerHeight - btnRect.bottom >= menuRect.height + gap
            || btnRect.top < menuRect.height + gap
        );
        const top = openDown
            ? Math.min(btnRect.bottom + gap, window.innerHeight - menuRect.height - margin)
            : Math.max(margin, btnRect.top - menuRect.height - gap);
        const left = Math.min(
            Math.max(margin, btnRect.right - menuRect.width),
            window.innerWidth - menuRect.width - margin
        );

        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        menu.style.visibility = '';
        menu.classList.toggle('drop-down', openDown);
    }

    document.addEventListener('click', e => {
        const btn = e.target.closest('.dropdown-toggle');
        if (!btn) {
            if (!e.target.closest('.dropdown-menu')) closeAll();
            return;
        }
        const menu = btn.nextElementSibling;
        if (!menu?.classList.contains('dropdown-menu')) return;
        const wasOpen = menu.classList.contains('open');
        closeAll();
        if (!wasOpen) {
            menu.classList.remove('drop-down');
            menu.classList.add('open');
            positionFloatingMenu(btn, menu);
            syncDropdownCard(menu);
        }
    });

    document.addEventListener('click', e => {
        if (e.target.closest('.dropdown-menu .dropdown-item')) {
            setTimeout(closeAll, 0);
        }
    });

    window.addEventListener('resize', closeAll);
    window.addEventListener('scroll', closeAll, true);

    const userBtn  = document.getElementById('user-menu-btn');
    const userMenu = document.getElementById('user-dropdown');
    if (userBtn) {
        userBtn.addEventListener('click', e => {
            e.stopPropagation();
            const wasOpen = userMenu.classList.contains('open');
            closeAll();
            if (!wasOpen) {
                // The account menu lives in the top bar, so it must always open downward.
                userMenu.classList.add('drop-down');
                userMenu.classList.add('open');
                const rect = userMenu.getBoundingClientRect();
                if (rect.right > window.innerWidth - 8) {
                    userMenu.style.right = '0';
                }
            }
        });
    }
})();

/* ── Modal ── */
document.addEventListener('click', event => {
    const el = event.target.closest('.thumb, .thumb-video');
    if (!el || el.dataset.previewDisabled === 'true') return;
    const mImg = document.getElementById('modal-img');
    const mVid = document.getElementById('modal-video');
    if (el.dataset.type === 'video') {
        mVid.src = el.dataset.src;
        mVid.classList.remove('u-hidden');
        mImg.classList.add('u-hidden');
        mVid.play();
    } else {
        mImg.src = el.dataset.src;
        mImg.classList.remove('u-hidden');
        mVid.classList.add('u-hidden');
        mVid.pause();
    }
    document.getElementById('modal').classList.add('open');
});
document.getElementById('modal-close').addEventListener('click', () => {
    document.getElementById('modal-video').pause();
    document.getElementById('modal').classList.remove('open');
});
document.getElementById('modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) { document.getElementById('modal-video').pause(); e.currentTarget.classList.remove('open'); }
});

if (window.ADMIN_LAYOUT_CONFIG && window.ADMIN_LAYOUT_CONFIG.globalQueueEnabled) {
/* ── Queue badge (global) ── */
async function updateQueueBadge() {
    try {
        const r = await fetch('/api/queue');
        const d = await r.json();
        const badge = document.getElementById('nav-queue-badge');
        if (badge) {
            const n = (d.active||[]).length;
            badge.style.display = n ? 'inline' : 'none';
            badge.textContent = n;
        }
    } catch {}
}
window.addEventListener('load', () => setTimeout(updateQueueBadge, 1200), { once: true });
setInterval(() => {
    if (document.visibilityState === 'visible') updateQueueBadge();
}, 45000);
}

/* ── Messages & confirmations ── */
(function() {
    const uiText = window.ADMIN_LAYOUT_CONFIG?.uiText || {};
    const text = (key, fallback) => uiText[key] || fallback;
    const contentShell = document.querySelector('.content-shell');
    const dialog = document.getElementById('app-feedback-dialog');
    const icon = document.getElementById('app-feedback-icon');
    const title = document.getElementById('app-feedback-title');
    const message = document.getElementById('app-feedback-message');
    const body = document.getElementById('app-feedback-body');
    const actions = document.getElementById('app-feedback-actions');
    const cancelBtn = document.getElementById('app-feedback-cancel');
    const confirmBtn = document.getElementById('app-feedback-confirm');
    const icons = {
        info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><circle cx="12" cy="12" r="10"/><line x1="12" y1="10" x2="12" y2="16"/><line x1="12" y1="7" x2="12.01" y2="7"/></svg>',
        success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>',
        warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><path d="M12 3 2 21h20L12 3z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
        error: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    };
    let resolver = null;
    let previouslyFocused = null;

    function escapeHtml(value) {
        return String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function closeDialog(result) {
        if (!resolver) return;
        const done = resolver;
        resolver = null;
        dialog.classList.remove('open');
        dialog.setAttribute('aria-hidden', 'true');
        body.innerHTML = '';
        previouslyFocused?.focus?.();
        previouslyFocused = null;
        done(result);
    }

    function openDialog(options = {}) {
        const {
            kind = 'confirm',
            tone = 'info',
            titleText = kind === 'confirm' ? text('dialogTitleConfirm', 'Confirmation') : text('dialogTitleInfo', 'Information'),
            messageText = '',
            note = '',
            confirmLabel = kind === 'confirm' ? text('dialogConfirm', 'Confirmer') : text('dialogClose', 'Fermer'),
            cancelLabel = text('dialogCancel', 'Annuler'),
            confirmClass = tone === 'error' ? 'danger' : tone === 'warning' ? 'warning' : '',
        } = options;

        icon.dataset.tone = tone;
        icon.innerHTML = icons[tone] || icons.info;
        title.textContent = titleText;
        message.textContent = messageText;
        body.innerHTML = note
            ? `<div class="theme-dialog-note" data-tone="${tone === 'success' ? 'info' : tone}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg><div><strong>${escapeHtml(text('dialogNoteTitle', 'À savoir'))}</strong><p>${escapeHtml(note)}</p></div></div>`
            : '';
        cancelBtn.style.display = kind === 'confirm' ? '' : 'none';
        cancelBtn.textContent = cancelLabel;
        confirmBtn.textContent = confirmLabel;
        confirmBtn.className = `btn sm${confirmClass ? ` ${confirmClass}` : ''}`;

        previouslyFocused = document.activeElement;
        dialog.classList.add('open');
        dialog.setAttribute('aria-hidden', 'false');
        requestAnimationFrame(() => confirmBtn.focus());

        return new Promise(resolve => {
            resolver = resolve;
        });
    }

    cancelBtn.addEventListener('click', () => closeDialog(false));
    confirmBtn.addEventListener('click', () => closeDialog(true));
    dialog.addEventListener('click', event => {
        if (event.target === dialog) {
            closeDialog(false);
        }
    });
    document.addEventListener('keydown', event => {
        if (dialog.getAttribute('aria-hidden') !== 'false') return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeDialog(false);
        }
    });

    window.appUI = {
        showFlash(messageText, type = 'info', options = {}) {
            if (!options.blocking) {
                showToast(messageText, type);
                return Promise.resolve(true);
            }
            const titles = { success: text('flashTitleSuccess', 'Succès'), error: text('flashTitleError', 'Erreur'), warning: text('flashTitleWarning', 'Avertissement'), info: text('flashTitleInfo', 'Information') };
            return openDialog({ kind: 'alert', messageText, tone: type, titleText: titles[type] || text('flashTitleInfo', 'Information'), confirmLabel: text('dialogClose', 'Fermer'), ...options });
        },
        showFlashAfterReload(messageText, type = 'info') {
            try {
                window.sessionStorage.setItem('app.pendingFlash', JSON.stringify({ msg: messageText, tone: type }));
            } catch {}
        },
        confirm(options) {
            const normalized = typeof options === 'string' ? { messageText: options } : options;
            return openDialog({ kind: 'confirm', tone: 'warning', ...normalized });
        },
        alert(messageText, options = {}) {
            return openDialog({ kind: 'alert', messageText, ...options });
        },
    };

    function showToast(msg, tone) {
        let list = document.getElementById('flash-toast-list');
        if (!list) {
            list = document.createElement('ul');
            list.id = 'flash-toast-list';
            list.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9000;list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px;max-width:400px;width:calc(100% - 48px)';
            document.body.appendChild(list);
        }
        const item = document.createElement('li');
        item.style.cssText = 'padding:13px 16px;border-radius:14px;font-size:.86rem;font-weight:600;display:flex;align-items:center;gap:10px;border:1px solid;box-shadow:var(--dialog-panel-shadow);transition:opacity .2s,transform .2s;background:var(--dialog-panel-bg);backdrop-filter:blur(5px) saturate(1.08);-webkit-backdrop-filter:blur(5px) saturate(1.08)';
        const colors = { success: 'var(--success-text)', info: 'var(--info-text)' };
        const borders = { success: 'var(--success-border)', info: 'var(--info-border)' };
        item.style.color = colors[tone] || 'var(--info-text)';
        item.style.borderColor = borders[tone] || 'var(--info-border)';
        const text = document.createElement('span');
        text.style.flex = '1';
        text.textContent = msg;
        const close = document.createElement('button');
        close.type = 'button';
        close.style.cssText = 'width:24px;height:24px;border:0;background:transparent;cursor:pointer;color:inherit;opacity:.6;display:flex;align-items:center;justify-content:center;border-radius:6px';
        close.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" style="width:14px;height:14px"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
        close.addEventListener('click', () => item.remove());
        item.append(text, close);
        list.appendChild(item);
        setTimeout(() => { item.style.opacity = '0'; item.style.transform = 'translateY(6px)'; setTimeout(() => item.remove(), 220); }, 4000);
    }

    try {
        const pendingFlash = window.sessionStorage.getItem('app.pendingFlash');
        if (pendingFlash) {
            window.sessionStorage.removeItem('app.pendingFlash');
            const parsed = JSON.parse(pendingFlash);
            if (parsed && parsed.msg) {
                showToast(parsed.msg, parsed.tone || 'info');
            }
        }
    } catch {}

    if (window.__flashMessages && window.__flashMessages.length) {
        const blocking = window.__flashMessages.filter(f => f.tone === 'error' || f.tone === 'warning');
        const passive  = window.__flashMessages.filter(f => f.tone === 'success' || f.tone === 'info');
        passive.forEach(f => showToast(f.msg, f.tone));
        (async () => {
            for (const f of blocking) {
                await openDialog({ kind: 'alert', messageText: f.msg, tone: f.tone, titleText: f.title, confirmLabel: text('dialogClose', 'Fermer') });
            }
        })();
    }

    document.addEventListener('submit', async event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (!form.dataset.confirm || form.dataset.confirmBypass === 'true') {
            delete form.dataset.confirmBypass;
            return;
        }
        event.preventDefault();
        const ok = await window.appUI.confirm({
            titleText: form.dataset.confirmTitle || text('dialogTitleConfirm', 'Confirmation'),
            messageText: form.dataset.confirm,
            note: form.dataset.confirmNote || '',
            tone: form.dataset.confirmTone || 'warning',
            confirmLabel: form.dataset.confirmOk || text('dialogConfirm', 'Confirmer'),
            cancelLabel: form.dataset.confirmCancel || text('dialogCancel', 'Annuler'),
        });
        if (ok) {
            form.dataset.confirmBypass = 'true';
            form.requestSubmit();
        }
    });
})();
