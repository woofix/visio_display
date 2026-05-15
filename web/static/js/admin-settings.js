const adminSettingsConfigEl = document.getElementById('admin-settings-config');
const adminSettingsConfig = adminSettingsConfigEl ? JSON.parse(adminSettingsConfigEl.textContent || '{}') : {};
const adminSettingsI18n = adminSettingsConfig.i18n || {};

(function() {
    const sel = document.getElementById('install-screen-url-select');
    const serverUrlInput = document.getElementById('install-server-url');
    const screenNameInput = document.getElementById('install-screen-name');
    if (!sel) return;
    const base = window.location.origin;
    const screenToken = adminSettingsConfig.displayApiToken || '';
    function buildUrl(screen) {
        const params = new URLSearchParams();
        if (screen) params.set('screen', screen);
        params.set(adminSettingsConfig.screenTokenParam || 'screen_token', screenToken);
        return base + '/?' + params.toString();
    }
    // options already have screen names as textContent from Jinja
    function sync() {
        const screen = sel.value;
        if (serverUrlInput) serverUrlInput.value = buildUrl(screen);
        if (screenNameInput) screenNameInput.value = screen;
    }
    sel.addEventListener('change', sync);
    sync();
})();

(function() {
    const fillHostField = (form, host) => {
        if (!form) return;
        const hostInput = form.querySelector('input[name="host"]');
        const hostSelect = form.querySelector('select[name="host"]');
        if (hostInput) {
            hostInput.value = host || '';
            hostInput.focus();
            hostInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
        if (hostSelect) {
            const desired = host || '';
            const existing = Array.from(hostSelect.options).find(option => option.value === desired);
            if (existing) {
                hostSelect.value = desired;
            }
            hostSelect.focus();
            hostSelect.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    };

    document.querySelectorAll('.btn-use-client').forEach(btn => {
        btn.addEventListener('click', () => {
            const form = document.getElementById(btn.dataset.targetForm || '');
            if (!form) return;
            fillHostField(form, btn.dataset.host || '');
        });
    });
})();

(function() {
    const list = document.getElementById('known-clients-list');
    const empty = document.getElementById('known-clients-empty');
    if (!list) return;

    const texts = {
        hostname: adminSettingsI18n.knownClientsHostname || '',
        screen: adminSettingsI18n.knownClientsScreen || '',
        lastSeen: adminSettingsI18n.knownClientsLastSeen || '',
        countdown: adminSettingsI18n.knownClientsCountdown || '',
        online: adminSettingsI18n.knownClientsStatusOnline || '',
        offline: adminSettingsI18n.knownClientsStatusOffline || '',
        healthy: adminSettingsI18n.knownClientsHealthHealthy || '',
        attention: adminSettingsI18n.knownClientsHealthAttention || '',
        critical: adminSettingsI18n.knownClientsHealthCritical || '',
        version: adminSettingsI18n.knownClientsVersion || '',
        uptime: adminSettingsI18n.knownClientsUptime || '',
        cpu: adminSettingsI18n.knownClientsCpu || '',
        ram: adminSettingsI18n.knownClientsRam || '',
        temperature: adminSettingsI18n.knownClientsTemperature || '',
        disk: adminSettingsI18n.knownClientsDisk || '',
        resolution: adminSettingsI18n.knownClientsResolution || '',
        lastError: adminSettingsI18n.knownClientsLastError || '',
        unavailable: adminSettingsI18n.knownClientsUnavailable || '',
        showDetails: adminSettingsI18n.knownClientsShowDetails || '',
        hideDetails: adminSettingsI18n.knownClientsHideDetails || '',
        diskFreeSuffix: adminSettingsI18n.knownClientsDiskFreeSuffix || '',
        useInstall: adminSettingsI18n.knownClientsUseInstall || '',
        useControl: adminSettingsI18n.knownClientsUseControl || '',
        empty: adminSettingsI18n.knownClientsEmpty || '',
        unknownIp: 'IP inconnue',
    };

    const formatCountdown = (seconds) => {
        const safe = Math.max(0, Number(seconds) || 0);
        const minutes = Math.floor(safe / 60);
        const remain = safe % 60;
        if (minutes <= 0) return `${remain}s`;
        return `${minutes}m ${String(remain).padStart(2, '0')}s`;
    };

    const formatLastSeen = (value) => {
        if (!value) return '';
        const ts = Date.parse(value);
        if (Number.isNaN(ts)) return '';
        const deltaSeconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
        if (deltaSeconds < 60) return `${deltaSeconds}s`;
        const minutes = Math.floor(deltaSeconds / 60);
        if (minutes < 60) return `${minutes} min`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours} h`;
        const days = Math.floor(hours / 24);
        return `${days} j`;
    };

    const syncEmptyState = () => {
        const hasCards = Boolean(list.querySelector('[data-client-card]'));
        list.style.display = hasCards ? '' : 'none';
        if (empty) empty.style.display = hasCards ? 'none' : 'block';
    };

    const escapeHtml = (value) => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');

    const bindUseClientButtons = (root) => {
        root.querySelectorAll('.btn-use-client').forEach(btn => {
            btn.addEventListener('click', () => {
                const form = document.getElementById(btn.dataset.targetForm || '');
                if (!form) return;
                const hostInput = form.querySelector('input[name="host"]');
                const hostSelect = form.querySelector('select[name="host"]');
                if (hostInput) {
                    hostInput.value = btn.dataset.host || '';
                    hostInput.focus();
                    hostInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    return;
                }
                if (hostSelect) {
                    const desired = btn.dataset.host || '';
                    const existing = Array.from(hostSelect.options).find(option => option.value === desired);
                    if (existing) {
                        hostSelect.value = desired;
                    }
                    hostSelect.focus();
                    hostSelect.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        });
    };

    const bindClientDetailsToggles = (root) => {
        root.querySelectorAll('[data-client-toggle]').forEach((btn) => {
            if (btn.dataset.bound === '1') return;
            btn.dataset.bound = '1';
            btn.addEventListener('click', () => {
                const card = btn.closest('[data-client-card]');
                if (!card) return;
                const expanded = card.dataset.expanded === 'true';
                card.dataset.expanded = expanded ? 'false' : 'true';
                btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                btn.textContent = expanded ? texts.showDetails : texts.hideDetails;
            });
        });
    };

    const formatPercent = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)}%` : texts.unavailable;
    const formatTemperature = (value) => Number.isFinite(Number(value)) ? `${Number(value).toFixed(1)} °C` : texts.unavailable;
    const formatRam = (client) => {
        if (!client.ram_used_human || !client.ram_total_human) return texts.unavailable;
        const percent = Number.isFinite(Number(client.ram_percent)) ? ` (${Number(client.ram_percent).toFixed(1)}%)` : '';
        return `${client.ram_used_human} / ${client.ram_total_human}${percent}`;
    };
    const formatDisk = (client) => {
        if (!client.disk_free_human || !client.disk_total_human) return texts.unavailable;
        const percent = Number.isFinite(Number(client.disk_percent)) ? ` (${Number(client.disk_percent).toFixed(1)}%)` : '';
        return `${client.disk_free_human} ${texts.diskFreeSuffix} / ${client.disk_total_human}${percent}`;
    };
    const healthLabel = (status) => texts[status] || texts.healthy;
    const formatSummaryRam = (client) => Number.isFinite(Number(client.ram_percent))
        ? `${Number(client.ram_percent).toFixed(1)}%`
        : texts.unavailable;

    const renderClientCard = (client) => {
        const meta = [];
        if (client.hostname) meta.push(`${escapeHtml(texts.hostname)} ${escapeHtml(client.hostname)}`);
        meta.push(
            `${escapeHtml(texts.lastSeen)} <span data-client-last-seen data-last-seen="${escapeHtml(client.last_seen || '')}">${escapeHtml(formatLastSeen(client.last_seen) || client.last_seen_relative || '')}</span>`
        );
        meta.push(`${escapeHtml(texts.countdown)} <span data-client-countdown>${formatCountdown(client.seconds_until_hidden)}</span>`);

        return `
            <div class="known-client-item" data-client-card data-expanded="false" data-seconds-left="${Number(client.seconds_until_hidden) || 0}" data-health-status="${escapeHtml(client.health_status || 'healthy')}">
                <div class="known-client-head">
                    <div>
                        <div class="known-client-name">${escapeHtml(client.display_name || '')}</div>
                        <div class="known-client-meta">${meta.join('<br>')}</div>
                    </div>
                    <div class="known-client-health">
                        <span class="known-client-badge ${client.is_online ? 'online' : 'offline'}">
                            ${escapeHtml(client.is_online ? texts.online : texts.offline)}
                        </span>
                        <span class="known-client-badge ${escapeHtml(client.health_status || 'healthy')}">
                            ${escapeHtml(healthLabel(client.health_status || 'healthy'))}
                        </span>
                    </div>
                </div>
                <div class="known-client-ip">${escapeHtml(client.ip_address || texts.unknownIp)}</div>
                <div class="known-client-badges">
                    ${client.server_url ? `<span class="known-client-badge">${escapeHtml(client.server_url)}</span>` : ''}
                    ${client.machine_id ? `<span class="known-client-badge">${escapeHtml(client.machine_id)}</span>` : ''}
                </div>
                <div class="known-client-overview">
                    <div class="known-client-overview-item">
                        <div class="known-client-overview-label">${escapeHtml(texts.cpu)}</div>
                        <div class="known-client-overview-value">${escapeHtml(formatPercent(client.cpu_load_percent))}</div>
                    </div>
                    <div class="known-client-overview-item">
                        <div class="known-client-overview-label">${escapeHtml(texts.ram)}</div>
                        <div class="known-client-overview-value">${escapeHtml(formatSummaryRam(client))}</div>
                    </div>
                    <div class="known-client-overview-item">
                        <div class="known-client-overview-label">${escapeHtml(texts.uptime)}</div>
                        <div class="known-client-overview-value">${escapeHtml(client.uptime_human || texts.unavailable)}</div>
                    </div>
                </div>
                <button type="button" class="known-client-toggle" data-client-toggle aria-expanded="false">
                    ${escapeHtml(texts.showDetails)}
                </button>
                <div class="known-client-details">
                    <div class="known-client-metrics">
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.screen)}</div>
                            <div class="known-client-metric-value">${escapeHtml(client.screen_name || texts.unavailable)}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.version)}</div>
                            <div class="known-client-metric-value">${escapeHtml(client.client_version || texts.unavailable)}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.uptime)}</div>
                            <div class="known-client-metric-value">${escapeHtml(client.uptime_human || texts.unavailable)}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.resolution)}</div>
                            <div class="known-client-metric-value">${escapeHtml(client.resolution || texts.unavailable)}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.cpu)}</div>
                            <div class="known-client-metric-value">${escapeHtml(formatPercent(client.cpu_load_percent))}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.temperature)}</div>
                            <div class="known-client-metric-value">${escapeHtml(formatTemperature(client.temperature_c))}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.ram)}</div>
                            <div class="known-client-metric-value">${escapeHtml(formatRam(client))}</div>
                        </div>
                        <div class="known-client-metric">
                            <div class="known-client-metric-label">${escapeHtml(texts.disk)}</div>
                            <div class="known-client-metric-value">${escapeHtml(formatDisk(client))}</div>
                        </div>
                    </div>
                    ${client.last_error ? `<div class="known-client-error"><strong>${escapeHtml(texts.lastError)}</strong>${escapeHtml(client.last_error)}</div>` : ''}
                    <div class="known-client-actions">
                        <button type="button" class="btn secondary sm btn-use-client" data-target-form="install-client-form" data-host="${escapeHtml(client.ip_address || '')}">${escapeHtml(texts.useInstall)}</button>
                        <button type="button" class="btn sm btn-use-client" data-target-form="client-control-form" data-host="${escapeHtml(client.ip_address || '')}">${escapeHtml(texts.useControl)}</button>
                    </div>
                </div>
            </div>
        `;
    };

    const startCountdown = (card) => {
        if (card.dataset.timerBound === '1') return;
        card.dataset.timerBound = '1';
        const countdown = card.querySelector('[data-client-countdown]');
        const lastSeen = card.querySelector('[data-client-last-seen]');
        let secondsLeft = Number(card.dataset.secondsLeft || 0);
        if (countdown) countdown.textContent = formatCountdown(secondsLeft);
        if (lastSeen) lastSeen.textContent = formatLastSeen(lastSeen.dataset.lastSeen || '') || lastSeen.textContent;

        const timer = window.setInterval(() => {
            secondsLeft -= 1;
            if (lastSeen) {
                lastSeen.textContent = formatLastSeen(lastSeen.dataset.lastSeen || '') || lastSeen.textContent;
            }
            if (secondsLeft <= 0) {
                window.clearInterval(timer);
                card.remove();
                syncEmptyState();
                return;
            }
            card.dataset.secondsLeft = String(secondsLeft);
            if (countdown) countdown.textContent = formatCountdown(secondsLeft);
        }, 1000);
    };

    const renderClients = (clients) => {
        list.innerHTML = (clients || []).map(renderClientCard).join('');
        list.querySelectorAll('[data-client-card]').forEach(startCountdown);
        bindUseClientButtons(list);
        bindClientDetailsToggles(list);
        syncEmptyState();
    };

    list.querySelectorAll('[data-client-card]').forEach((card) => {
        startCountdown(card);
    });
    bindClientDetailsToggles(list);

    syncEmptyState();

    let refreshInFlight = false;
    const refreshClients = async () => {
        if (refreshInFlight) return;
        refreshInFlight = true;
        try {
            const resp = await fetch('/admin/settings/known-clients', { cache: 'no-store' });
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data.ok) return;
            renderClients(data.clients || []);
        } catch (e) {
            // Keep the current view if a refresh fails temporarily.
        } finally {
            refreshInFlight = false;
        }
    };

    window.setInterval(refreshClients, 10000);
})();

document.querySelectorAll('.theme-card input[type=radio]').forEach(radio => {
    radio.addEventListener('change', () => {
        document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('selected'));
        radio.closest('.theme-card').classList.add('selected');
        if (typeof window.applyThemePreference === 'function') {
            window.applyThemePreference(radio.value);
        } else {
            document.documentElement.dataset.theme = radio.value;
        }
    });
});

(function() {
    const remoteCopyEnabled = !!adminSettingsConfig.remoteCopyEnabled;
    const form = document.getElementById('backup-create-form');
    const button = document.getElementById('backup-create-btn');
    const label = document.getElementById('backup-create-label');
    const loadingBox = document.getElementById('backup-create-loading-box');
    const logBox = document.getElementById('backup-create-log');
    const list = document.querySelector('#sauvegardes .backup-list');
    const emptyState = document.querySelector('#sauvegardes .backup-empty');
    if (!form || !button || !label || !loadingBox || !logBox) return;

    const escapeHtml = (value) => String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');

    const appendLog = (message, isError = false) => {
        const line = document.createElement('div');
        line.className = `backup-log-line${isError ? ' is-error' : ''}`;
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        line.textContent = `[${hh}:${mm}:${ss}] ${message}`;
        logBox.appendChild(line);
        logBox.scrollTop = logBox.scrollHeight;
    };

    const renderBackupItem = (backup) => {
        const createdAt = String(backup.created_at_iso || '').replace('T', ' ').slice(0, 19);
        const sizeBytes = Number(backup.size_bytes || backup.size || 0);
        const sizeMo = (sizeBytes / 1048576).toFixed(1);
        return `
            <div class="backup-item">
                <div class="backup-item-main">
                    <div class="backup-item-name">${escapeHtml(backup.filename)}</div>
                    <div class="backup-item-meta">${escapeHtml(createdAt)} UTC · ${escapeHtml(sizeMo)} Mo</div>
                </div>
                <div class="backup-item-actions">
                    <a class="btn sm secondary" href="/admin/settings/backups/download/${encodeURIComponent(backup.filename)}">${adminSettingsI18n.backupDownloadBtn || ''}</a>
                    ${remoteCopyEnabled ? `
                    <form method="post" action="/admin/settings/backups/copy/${encodeURIComponent(backup.filename)}">
                        <input type="hidden" name="_csrf_token" value="${escapeHtml(window.CSRF_TOKEN || '')}">
                        <button type="submit" class="btn sm secondary">${adminSettingsI18n.backupCopyBtn || ''}</button>
                    </form>
                    ` : ''}
                    <form method="post" action="/admin/settings/backups/delete/${encodeURIComponent(backup.filename)}" class="backup-delete-form" data-backup-filename="${escapeHtml(backup.filename)}">
                        <input type="hidden" name="_csrf_token" value="${escapeHtml(window.CSRF_TOKEN || '')}">
                        <button type="submit" class="btn sm danger">${adminSettingsI18n.backupDeleteBtn || ''}</button>
                    </form>
                </div>
            </div>
        `;
    };

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        button.disabled = true;
        button.classList.add('loading');
        label.innerHTML = `<span class="btn-spinner"></span> ${adminSettingsI18n.backupLoadingButton || ''}`;
        loadingBox.style.display = 'block';
        logBox.style.display = 'block';
        logBox.innerHTML = '';
        appendLog(adminSettingsI18n.backupStreamStart || '');

        try {
            const response = await fetch('/admin/settings/backups/create-stream', {
                method: 'POST',
                headers: {
                    'X-CSRF-Token': window.CSRF_TOKEN,
                    'Accept': 'application/x-ndjson',
                },
            });
            if (!response.ok || !response.body) {
                throw new Error(adminSettingsI18n.backupStreamError || '');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let createdBackup = null;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.trim()) continue;
                    const payload = JSON.parse(line);
                    if (payload.type === 'log') {
                        appendLog(payload.message || '');
                    } else if (payload.type === 'error') {
                        appendLog(payload.message || adminSettingsI18n.backupStreamError || '', true);
                    } else if (payload.type === 'done' && payload.backup) {
                        createdBackup = payload.backup;
                        appendLog(adminSettingsI18n.backupStreamSuccess || '');
                    }
                }
            }

            if (createdBackup) {
                if (emptyState) emptyState.remove();
                if (list) {
                    list.insertAdjacentHTML('afterbegin', renderBackupItem(createdBackup));
                } else {
                    window.location.reload();
                    return;
                }
            }
        } catch (error) {
            appendLog(error?.message || adminSettingsI18n.backupStreamError || '', true);
        } finally {
            button.disabled = false;
            button.classList.remove('loading');
            label.textContent = adminSettingsI18n.backupCreateBtn || '';
            loadingBox.style.display = 'none';
        }
    });
})();

(function() {
    const modal = document.getElementById('backup-delete-modal');
    const fileBox = document.getElementById('backup-delete-file');
    const cancelBtn = document.getElementById('backup-delete-cancel');
    const confirmBtn = document.getElementById('backup-delete-confirm');
    if (!modal || !fileBox || !cancelBtn || !confirmBtn) return;

    let pendingForm = null;

    const closeModal = () => {
        modal.setAttribute('aria-hidden', 'true');
        pendingForm = null;
    };

    const openModal = (form) => {
        pendingForm = form;
        fileBox.textContent = form?.dataset?.backupFilename || '';
        modal.setAttribute('aria-hidden', 'false');
    };

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.classList.contains('backup-delete-form')) return;
        if (form.dataset.confirmed === 'true') {
            delete form.dataset.confirmed;
            return;
        }
        event.preventDefault();
        openModal(form);
    });

    cancelBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (event) => {
        if (event.target === modal) closeModal();
    });
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && modal.getAttribute('aria-hidden') === 'false') {
            closeModal();
        }
    });

    confirmBtn.addEventListener('click', () => {
        if (!pendingForm) return;
        pendingForm.dataset.confirmed = 'true';
        pendingForm.requestSubmit();
        closeModal();
    });
})();

(function() {
    const form = document.getElementById('install-client-form');
    const button = document.getElementById('install-submit-btn');
    const label = document.getElementById('install-submit-label');
    const loadingBox = document.getElementById('install-loading-box');
    if (!form || !button || !label || !loadingBox) return;

    form.addEventListener('submit', () => {
        button.disabled = true;
        button.classList.add('loading');
        label.innerHTML = `<span class="btn-spinner"></span> ${adminSettingsI18n.installLoadingButton || ''}`;
        loadingBox.style.display = 'block';
    });
})();

(function() {
    const form = document.getElementById('client-control-form');
    const shutdownBtn = document.getElementById('client-shutdown-btn');
    const restartBtn = document.getElementById('client-restart-btn');
    const updateBtn = document.getElementById('client-update-btn');
    const osUpdateBtn = document.getElementById('client-os-update-btn');
    const shutdownLabel = document.getElementById('client-shutdown-label');
    const restartLabel = document.getElementById('client-restart-label');
    const updateLabel = document.getElementById('client-update-label');
    const osUpdateLabel = document.getElementById('client-os-update-label');
    const actionInput = document.getElementById('client-action-input');
    if (!form || !shutdownBtn || !restartBtn || !updateBtn || !osUpdateBtn || !shutdownLabel || !restartLabel || !updateLabel || !osUpdateLabel || !actionInput) return;

    shutdownBtn.addEventListener('click', () => {
        actionInput.value = 'shutdown';
    });
    restartBtn.addEventListener('click', () => {
        actionInput.value = 'restart';
    });
    updateBtn.addEventListener('click', () => {
        actionInput.value = 'update';
    });
    osUpdateBtn.addEventListener('click', () => {
        actionInput.value = 'os-update';
    });

    form.addEventListener('submit', event => {
        const submitter = event.submitter;
        const actionValue = submitter?.dataset?.actionValue || actionInput.value;
        if (!actionValue) return;
        actionInput.value = actionValue;

        shutdownBtn.disabled = true;
        restartBtn.disabled = true;
        updateBtn.disabled = true;
        osUpdateBtn.disabled = true;
        shutdownBtn.classList.add('loading');
        restartBtn.classList.add('loading');
        updateBtn.classList.add('loading');
        osUpdateBtn.classList.add('loading');

        if (actionValue === 'shutdown') {
            shutdownLabel.innerHTML = `<span class="btn-spinner"></span> ${adminSettingsI18n.clientControlShutdownLoading || ''}`;
        } else if (actionValue === 'restart') {
            restartLabel.innerHTML = `<span class="btn-spinner"></span> ${adminSettingsI18n.clientControlRestartLoading || ''}`;
        } else if (actionValue === 'update') {
            updateLabel.innerHTML = `<span class="btn-spinner"></span> ${adminSettingsI18n.clientControlUpdateLoading || ''}`;
        } else {
            osUpdateLabel.innerHTML = `<span class="btn-spinner"></span> ${adminSettingsI18n.clientControlOsUpdateLoading || ''}`;
        }
    });
})();

/* ── City search via the Open-Meteo geocoding API ── */
async function searchMeteoCity() {
    const query   = document.getElementById('meteo-search-input').value.trim();
    const results = document.getElementById('meteo-search-results');
    if (!query) return;

    const btn = document.getElementById('meteo-search-btn');
    btn.disabled = true;
    results.style.display = 'none';
    results.innerHTML = '';

    try {
        const resp = await fetch(
            `https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(query)}&count=8&format=json`
        );
        const data = await resp.json();
        const list = data.results || [];

        if (!list.length) {
            results.innerHTML = `<div style="padding:10px 14px;font-size:.82rem;color:var(--text-3)">${escapeMeteoHtml(adminSettingsI18n.geocodeEmpty || 'No result found.')}</div>`;
            results.style.display = 'block';
            return;
        }

        results.innerHTML = list.map((item, i) => {
            const name    = item.name || '';
            const country = item.country || '';
            const admin   = item.admin1 ? `, ${item.admin1}` : '';
            const tz      = item.timezone || 'UTC';
            const lat     = item.latitude.toFixed(4);
            const lng     = item.longitude.toFixed(4);
            const safeName = escapeMeteoHtml(name);
            const safeCountry = escapeMeteoHtml(country);
            const safeAdmin = escapeMeteoHtml(admin);
            const safeTz = escapeMeteoHtml(tz);
            return `<div class="meteo-result-row" data-ville="${safeName}" data-lat="${escapeMeteoHtml(lat)}" data-lng="${escapeMeteoHtml(lng)}" data-tz="${safeTz}"
                         style="padding:10px 14px;cursor:pointer;border-bottom:1px solid var(--border);font-size:.84rem;display:flex;justify-content:space-between;align-items:center"
                         onmouseenter="this.style.background='var(--surface-alt)'" onmouseleave="this.style.background=''">
                        <span><strong>${safeName}</strong>${safeAdmin} — ${safeCountry}</span>
                        <span style="color:var(--text-3);font-size:.74rem">${escapeMeteoHtml(lat)}, ${escapeMeteoHtml(lng)}</span>
                    </div>`;
        }).join('');

        results.querySelectorAll('.meteo-result-row').forEach(row => {
            row.addEventListener('click', () => {
                document.getElementById('meteo-ville').value = row.dataset.ville;
                document.getElementById('meteo-lat').value   = row.dataset.lat;
                document.getElementById('meteo-lng').value   = row.dataset.lng;
                document.getElementById('meteo-tz').value    = row.dataset.tz;
                results.style.display = 'none';
            });
        });

        results.style.display = 'block';
    } catch (e) {
        results.innerHTML = `<div style="padding:10px 14px;font-size:.82rem;color:var(--red)">${escapeMeteoHtml(adminSettingsI18n.geocodeError || 'Error connecting to the geocoding API.')}</div>`;
        results.style.display = 'block';
    } finally {
        btn.disabled = false;
    }
}

function escapeMeteoHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

/* Search when Enter is pressed in the field */
document.getElementById('meteo-search-input')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); searchMeteoCity(); }
});

/* Close the results when clicking outside */
document.addEventListener('click', e => {
    const results = document.getElementById('meteo-search-results');
    if (results && !results.contains(e.target) && e.target.id !== 'meteo-search-input' && e.target.id !== 'meteo-search-btn') {
        results.style.display = 'none';
    }
});

document.querySelectorAll('.screen-halo-picker').forEach(input => {
    const value = input.parentElement.querySelector('.screen-halo-value');
    const sync = () => {
        if (value) value.textContent = (input.value || '').toUpperCase();
    };
    input.addEventListener('input', sync);
    sync();
});

function notifyDisplayRefresh(type) {
    try {
        localStorage.setItem('visio-display:media-refresh', String(Date.now()));
    } catch (e) {
        // localStorage may be unavailable in some private browsing contexts.
    }
    if (!('BroadcastChannel' in window)) return;
    const channel = new BroadcastChannel('visio-display-media');
    channel.postMessage({ type });
    channel.close();
}

document.querySelectorAll('.screen-halo-form').forEach(form => {
    form.addEventListener('submit', () => notifyDisplayRefresh('media-refresh'));
});

/* ── Superadmin: priority alert ── */
(function() {
    const priorityAlertInput = document.getElementById('priority-alert-input');
    if (!priorityAlertInput) return;
    const priorityAlertStatus = document.getElementById('priority-alert-status');
    const priorityAlertPreview = document.getElementById('priority-alert-preview');
    const priorityAlertPreviewBody = document.getElementById('priority-alert-preview-body');
    const priorityAlertClear = document.getElementById('priority-alert-clear');

    let priorityAlertTimer = null;
    let priorityAlertController = null;
    let lastSavedPriorityAlert = priorityAlertInput.value.trim();

    function renderPriorityAlertPreview(message) {
        if (!priorityAlertPreview || !priorityAlertPreviewBody) return;
        priorityAlertPreviewBody.textContent = message;
        priorityAlertPreview.style.display = message ? 'block' : 'none';
    }

    function setPriorityAlertStatus(message, isError = false) {
        if (!priorityAlertStatus) return;
        priorityAlertStatus.textContent = message;
        priorityAlertStatus.style.color = isError ? '#b91c1c' : 'var(--text-3)';
    }

    async function pushPriorityAlert(message) {
        if (priorityAlertController) priorityAlertController.abort();
        priorityAlertController = new AbortController();
        setPriorityAlertStatus(adminSettingsI18n.priorityAlertSaving || '');
        try {
            const res = await fetch('/admin/priority-alert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8' },
                body: new URLSearchParams({ message }),
                signal: priorityAlertController.signal
            });
            if (!res.ok) throw new Error('save_failed');
            const data = await res.json();
            lastSavedPriorityAlert = data.message || '';
            priorityAlertInput.value = lastSavedPriorityAlert;
            renderPriorityAlertPreview(lastSavedPriorityAlert);
            setPriorityAlertStatus(lastSavedPriorityAlert ? adminSettingsI18n.priorityAlertSaved || '' : adminSettingsI18n.priorityAlertCleared || '');
        } catch (err) {
            if (err.name === 'AbortError') return;
            setPriorityAlertStatus(adminSettingsI18n.priorityAlertError || '', true);
        }
    }

    function schedulePriorityAlertSave() {
        const message = priorityAlertInput.value.trim().replace(/\s+/g, ' ');
        renderPriorityAlertPreview(message);
        if (message === lastSavedPriorityAlert) { setPriorityAlertStatus(''); return; }
        clearTimeout(priorityAlertTimer);
        setPriorityAlertStatus(adminSettingsI18n.priorityAlertPending || '');
        priorityAlertTimer = setTimeout(() => pushPriorityAlert(message), 250);
    }

    priorityAlertInput.addEventListener('input', schedulePriorityAlertSave);
    renderPriorityAlertPreview(lastSavedPriorityAlert);

    if (priorityAlertClear) {
        priorityAlertClear.addEventListener('click', () => {
            priorityAlertInput.value = '';
            schedulePriorityAlertSave();
        });
    }
})();

function toggleAll(btn) {
    const form = btn.closest('form');
    const boxes = form.querySelectorAll('input[type=checkbox]');
    const allChecked = Array.from(boxes).every(b => b.checked);
    boxes.forEach(b => b.checked = !allChecked);
    btn.textContent = allChecked ? adminSettingsI18n.superadminCheckAll || '' : adminSettingsI18n.superadminUncheckAll || '';
}

function toggleResetForm(btn) {
    const section = btn.closest('.reset-pass-section');
    const form = section.querySelector('.reset-pass-form');
    const isVisible = form.style.display !== 'none';
    form.style.display = isVisible ? 'none' : 'flex';
}
