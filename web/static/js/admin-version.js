(function() {
    const panel = document.getElementById('server-update-panel');
    if (!panel) return;

    const checkBtn = document.getElementById('update-check-btn');
    const applyBtn = document.getElementById('update-apply-btn');
    const restartBtn = document.getElementById('update-restart-btn');
    const stateBox = document.getElementById('update-state');
    const label = document.getElementById('update-status-label');
    const reason = document.getElementById('update-status-reason');
    const checksBox = document.getElementById('update-checks');
    const confirmBox = document.getElementById('update-confirm');
    const logBox = document.getElementById('update-log');

    const fields = {
        local_version: document.getElementById('update-local-version'),
        remote_version: document.getElementById('update-remote-version'),
        target_branch: document.getElementById('update-target-branch'),
        git_state: document.getElementById('update-git-state'),
        local_commit: document.getElementById('update-local-commit'),
        remote_commit: document.getElementById('update-remote-commit'),
        remote: document.getElementById('update-remote'),
    };
    const refField = document.getElementById('update-ref');

    let currentStatus = {};
    const updateSteps = [
        { key: 'pull', label: 'Téléchargement / pull', state: 'active' },
        { key: 'stop', label: 'Arrêt des services', state: 'pending' },
        { key: 'restart', label: 'Redémarrage Docker', state: 'pending' },
        { key: 'containers', label: 'Vérification des conteneurs', state: 'pending' },
        { key: 'app', label: "Vérification de l'application", state: 'pending' },
    ];
    try {
        currentStatus = JSON.parse(panel.dataset.initialStatus || '{}');
    } catch (error) {
        currentStatus = {};
    }

    function text(value) {
        return value ? String(value) : '-';
    }

    function setBusy(isBusy) {
        checkBtn.disabled = isBusy;
        applyBtn.disabled = isBusy;
        restartBtn.disabled = isBusy;
    }

    function appendLog(message, isError) {
        logBox.hidden = false;
        const prefix = isError ? 'ERREUR: ' : '';
        logBox.textContent += `${prefix}${message || ''}\n`;
        logBox.scrollTop = logBox.scrollHeight;
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    async function pollRuntimeStatus() {
        const deadline = Date.now() + 8 * 60 * 1000;
        while (Date.now() < deadline) {
            try {
                const response = await fetch('/admin/version/update/runtime-status', {
                    headers: { 'Accept': 'application/json' },
                    cache: 'no-store',
                });
                if (!response.ok) throw new Error('runtime unavailable');
                const payload = await response.json();
                if (!payload.ok) throw new Error(payload.error || 'runtime unavailable');
                const system = payload.system || {};
                const runtime = payload.runtime || {};
                if (system.active) {
                    window.adminSystemLock?.refresh();
                } else if (runtime.ready) {
                    appendLog('Application disponible.');
                    window.adminSystemLock?.hide();
                    await refreshStatus(false);
                    return true;
                }
            } catch {
                window.adminSystemLock?.showConnecting();
            }
            await sleep(2000);
        }
        appendLog('Le redémarrage prend trop longtemps. Vérifiez Docker puis relancez une vérification.', true);
        renderStatus({
            ...currentStatus,
            status: 'error',
            status_label: 'Timeout de redémarrage',
            status_tone: 'danger',
            reason: 'Les conteneurs ou l’application ne sont pas revenus dans le délai prévu.',
            can_apply: false,
        });
        return false;
    }

    function renderStatus(status) {
        currentStatus = status || {};
        stateBox.dataset.tone = currentStatus.status_tone || 'warning';
        label.textContent = currentStatus.status_label || 'État inconnu';
        reason.textContent = currentStatus.reason || (
            currentStatus.status === 'update_available'
                ? 'Une confirmation est requise avant application.'
                : 'Aucune action automatique ne sera lancée.'
        );

        Object.keys(fields).forEach((key) => {
            fields[key].textContent = text(currentStatus[key]);
        });
        refField.textContent = text(currentStatus.branch || currentStatus.current_ref);

        checksBox.innerHTML = '';
        (currentStatus.checks || []).forEach((item) => {
            const row = document.createElement('div');
            row.className = 'update-check';
            row.dataset.ok = item.ok ? 'true' : 'false';

            const mark = document.createElement('span');
            mark.className = 'update-check-mark';

            const body = document.createElement('div');
            const title = document.createElement('strong');
            title.textContent = item.label || item.key || 'Vérification';
            body.appendChild(title);

            if (item.detail) {
                const detail = document.createElement('div');
                detail.className = 'update-check-detail';
                detail.textContent = item.detail;
                body.appendChild(detail);
            }

            row.appendChild(mark);
            row.appendChild(body);
            checksBox.appendChild(row);
        });

        const canApply = currentStatus.can_apply === true && ['update_available', 'branch_switch_required'].includes(currentStatus.status);
        applyBtn.hidden = !canApply;
        restartBtn.hidden = currentStatus.status !== 'restart_required';
        confirmBox.hidden = !canApply;
    }

    async function refreshStatus(fetchRemote) {
        setBusy(true);
        logBox.hidden = true;
        logBox.textContent = '';
        try {
            const response = await fetch(`/admin/version/update/status${fetchRemote ? '?fetch=1' : ''}`, {
                headers: { 'Accept': 'application/json' },
                cache: 'no-store',
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                throw new Error(payload.error || 'Vérification impossible.');
            }
            renderStatus(payload.status);
        } catch (error) {
            appendLog(error?.message || 'Vérification impossible.', true);
            renderStatus({
                status: 'error',
                status_label: 'Erreur',
                status_tone: 'danger',
                reason: error?.message || 'Vérification impossible.',
                checks: currentStatus.checks || [],
            });
        } finally {
            setBusy(false);
        }
    }

    async function streamAction(url, startMessage) {
        setBusy(true);
        const lockType = url.includes('restart') ? 'reboot' : 'update';
        if (lockType === 'update') {
            window.adminSystemLock?.showDetailed(lockType, startMessage, 5, updateSteps);
        } else {
            window.adminSystemLock?.show(lockType, startMessage, 5);
        }
        logBox.hidden = false;
        logBox.textContent = '';
        appendLog(startMessage);
        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Accept': 'application/x-ndjson',
                    'X-CSRF-Token': window.CSRF_TOKEN,
                },
            });
            if (!response.ok || !response.body) {
                let errorMessage = 'Action impossible.';
                try {
                    const payload = await response.json();
                    errorMessage = payload.error || errorMessage;
                } catch {}
                throw new Error(errorMessage);
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finalStatus = null;
            let failed = false;
            const returnsBeforeConnectionClose = lockType === 'reboot';

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
                        failed = true;
                        appendLog(payload.message || 'Action échouée.', true);
                    } else if (payload.type === 'done') {
                        finalStatus = payload.status;
                        if (returnsBeforeConnectionClose) {
                            try {
                                await reader.cancel();
                            } catch {}
                            break;
                        }
                    }
                }
                if (returnsBeforeConnectionClose && finalStatus) break;
            }

            if (failed) {
                renderStatus({
                    ...currentStatus,
                    status: 'error',
                    status_label: 'Erreur',
                    status_tone: 'danger',
                    reason: 'La mise à jour n’a pas abouti. Consultez les logs ci-dessous.',
                    can_apply: false,
                });
            } else if (finalStatus) {
                renderStatus(finalStatus);
                appendLog('Terminé.');
                window.adminSystemLock?.refresh();
                if (finalStatus.status === 'restart_scheduled') {
                    pollRuntimeStatus();
                }
            }
        } catch (error) {
            appendLog(error?.message || 'Action échouée.', true);
            window.adminSystemLock?.refresh();
            renderStatus({
                ...currentStatus,
                status: 'error',
                status_label: 'Erreur',
                status_tone: 'danger',
                reason: error?.message || 'Action échouée.',
                can_apply: false,
            });
        } finally {
            setBusy(false);
        }
    }

    checkBtn.addEventListener('click', () => refreshStatus(true));
    applyBtn.addEventListener('click', async () => {
        if (!await window.appUI.confirm({
            titleText: 'Appliquer la mise à jour',
            messageText: 'Appliquer maintenant la mise à jour serveur affichée ?',
            tone: 'warning',
            confirmLabel: 'Appliquer',
        })) return;
        streamAction('/admin/version/update/apply-stream', 'Application de la mise à jour...');
    });
    restartBtn.addEventListener('click', async () => {
        if (!await window.appUI.confirm({
            titleText: 'Redémarrer Docker',
            messageText: 'Redémarrer la stack Docker maintenant ?',
            tone: 'warning',
            confirmLabel: 'Redémarrer',
        })) return;
        streamAction('/admin/version/update/restart-stream', 'Redémarrage de la stack Docker...');
    });

    renderStatus(currentStatus);
})();
