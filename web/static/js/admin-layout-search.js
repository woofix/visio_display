/* ── Recherche globale (topbar) ── */
(function() {
    const input = document.getElementById('topbar-search-input');
    const dropdown = document.getElementById('topbar-search-dropdown');
    if (!input || !dropdown) return;

    let debounceTimer = null;
    let lastQuery = '';
    let focusIdx = -1;
    const uiText = window.ADMIN_LAYOUT_CONFIG?.uiText || {};
    const text = (key, fallback, params = {}) => {
        let value = uiText[key] || fallback;
        Object.keys(params).forEach(name => {
            value = value.replaceAll(`{${name}}`, params[name]).replaceAll(`__${name}__`, params[name]);
        });
        return value;
    };

    function escHtml(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    function getItems() {
        return dropdown.querySelectorAll('.tsd-item');
    }

    function setFocus(idx) {
        const items = getItems();
        items.forEach(el => el.classList.remove('focused'));
        focusIdx = Math.max(-1, Math.min(idx, items.length - 1));
        if (focusIdx >= 0) {
            items[focusIdx].classList.add('focused');
            items[focusIdx].scrollIntoView({ block: 'nearest' });
        }
    }

    function closeDropdown() {
        dropdown.classList.remove('open');
        focusIdx = -1;
    }

    const ICONS = {
        page:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/></svg>`,
        media:    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
        campaign: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 7V3m8 4V3"/><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 11h18"/></svg>`,
        config:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
        wiki:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>`,
        activity: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
        user:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
    };

    function renderResults(data, q) {
        const total = (data.pages||[]).length + (data.media||[]).length + (data.campaigns||[]).length
                    + (data.wiki||[]).length + (data.config||[]).length + (data.activity||[]).length + (data.users||[]).length;
        if (!total) {
            dropdown.innerHTML = `<div class="tsd-empty">${escHtml(text('searchNoResults', 'No results for "{query}"', { query: q }))}</div>`;
            dropdown.classList.add('open');
            return;
        }
        let html = '';

        if (data.pages && data.pages.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.page}${escHtml(text('searchPages', 'Site pages'))}</div>`;
            data.pages.forEach(p => {
                html += `<a class="tsd-item" href="${escHtml(p.url)}">
                    <div class="tsd-item-icon">${ICONS.page}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(p.title)}</div>
                        <div class="tsd-item-meta">${escHtml(p.desc)}</div>
                    </div>
                </a>`;
            });
            html += '</div>';
        }

        if (data.media && data.media.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.media}${escHtml(text('searchMedia', 'Media'))}</div>`;
            data.media.forEach(item => {
                html += `<a class="tsd-item" href="/admin/media">
                    <div class="tsd-item-icon">${ICONS.media}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(item.filename)}</div>
                        <div class="tsd-item-meta">${escHtml((item.ext||'').toUpperCase())}${item.disabled ? ' · ' + escHtml(text('searchDisabled', 'disabled')) : ''}</div>
                    </div>
                </a>`;
            });
            html += '</div>';
        }

        if (data.wiki && data.wiki.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.wiki}${escHtml(text('searchWiki', 'Wiki'))}</div>`;
            data.wiki.forEach(item => {
                html += `<a class="tsd-item" href="${escHtml(item.url)}">
                    <div class="tsd-item-icon">${ICONS.wiki}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(item.title)}</div>
                        <div class="tsd-item-meta">${escHtml(item.desc)}</div>
                    </div>
                </a>`;
            });
            html += '</div>';
        }

        if (data.campaigns && data.campaigns.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.campaign}${escHtml(text('searchCampaigns', 'Campaigns'))}</div>`;
            data.campaigns.forEach(c => {
                const badge = c.archived ? 'archived' : c.enabled ? 'active' : 'disabled';
                const label = c.archived ? text('searchCampaignArchived', 'Archived') : c.enabled ? text('searchCampaignActive', 'Active') : text('searchCampaignInactive', 'Inactive');
                const dateMeta = c.start_date || c.end_date
                    ? (c.start_date ? text('searchFrom', 'From {date}', { date: escHtml(c.start_date) }) : '') + (c.end_date ? text('searchTo', ' to {date}', { date: escHtml(c.end_date) }) : '')
                    : text('searchNoDate', 'No date');
                html += `<a class="tsd-item" href="/admin/campaigns?campaign=${escHtml(c.id)}">
                    <div class="tsd-item-icon">${ICONS.campaign}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(c.name)}</div>
                        <div class="tsd-item-meta">${dateMeta}</div>
                    </div>
                    <span class="tsd-item-badge ${badge}">${escHtml(label)}</span>
                </a>`;
            });
            html += '</div>';
        }

        if (data.config && data.config.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.config}${escHtml(text('searchConfig', 'Configuration'))}</div>`;
            data.config.forEach(item => {
                html += `<a class="tsd-item" href="${escHtml(item.url)}">
                    <div class="tsd-item-icon">${ICONS.config}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(item.title)}</div>
                        <div class="tsd-item-meta">${escHtml(item.desc)}</div>
                    </div>
                </a>`;
            });
            html += '</div>';
        }

        if (data.users && data.users.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.user}${escHtml(text('searchUsers', 'Users'))}</div>`;
            data.users.forEach(u => {
                html += `<a class="tsd-item" href="/admin/settings/comptes-permissions">
                    <div class="tsd-item-icon">${ICONS.user}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(u.username)}</div>
                        <div class="tsd-item-meta">${escHtml(u.superadmin ? text('roleSuperadmin', 'Super-admin') : text('roleAdmin', 'Administrator'))}</div>
                    </div>
                </a>`;
            });
            html += '</div>';
        }

        if (data.activity && data.activity.length) {
            html += `<div class="tsd-section"><div class="tsd-label">${ICONS.activity}${escHtml(text('searchActivity', 'Activity'))}</div>`;
            data.activity.forEach(log => {
                html += `<div class="tsd-item">
                    <div class="tsd-item-icon">${ICONS.activity}</div>
                    <div class="tsd-item-body">
                        <div class="tsd-item-name">${escHtml(log.action)}</div>
                        <div class="tsd-item-meta">${escHtml(log.username)} · ${escHtml((log.timestamp||'').slice(0,16).replace('T',' '))}${log.filename ? ' · ' + escHtml(log.filename) : ''}</div>
                    </div>
                </div>`;
            });
            html += '</div>';
        }

        html += `<div class="tsd-footer">
            <span class="tsd-footer-hint">${escHtml(text('searchFooterHint', '↑↓ navigate · Enter select'))}</span>
            <a class="tsd-footer-link" href="/admin/search?q=${encodeURIComponent(q)}">${escHtml(text('searchAllResults', 'All results →'))}</a>
        </div>`;

        dropdown.innerHTML = html;
        dropdown.classList.add('open');
        focusIdx = -1;
    }

    async function doSearch(q) {
        if (q.length < 2) { closeDropdown(); return; }
        if (q === lastQuery) return;
        lastQuery = q;
        dropdown.innerHTML = `<div class="tsd-loading">${escHtml(text('searchLoading', 'Searching…'))}</div>`;
        dropdown.classList.add('open');
        try {
            const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
            if (!r.ok) throw new Error('err');
            const data = await r.json();
            if (input.value.trim() === q) renderResults(data, q);
        } catch {
            closeDropdown();
        }
    }

    input.addEventListener('input', () => {
        const q = input.value.trim();
        if (!q) { closeDropdown(); lastQuery = ''; return; }
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => doSearch(q), 250);
    });

    input.addEventListener('keydown', e => {
        const items = getItems();
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setFocus(focusIdx + 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setFocus(focusIdx - 1);
        } else if (e.key === 'Enter') {
            if (focusIdx >= 0 && items[focusIdx]) {
                e.preventDefault();
                items[focusIdx].click();
                closeDropdown();
            }
        } else if (e.key === 'Escape') {
            closeDropdown();
            input.blur();
        }
    });

    document.addEventListener('click', e => {
        if (!e.target.closest('#topbar-search-wrap')) closeDropdown();
    });

    /* Raccourci clavier Cmd/Ctrl+K */
    document.addEventListener('keydown', e => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            input.focus();
            input.select();
        }
    });
})();
