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
    const configEl = document.getElementById('admin-version-config');
    const i18n = configEl ? JSON.parse(configEl.textContent || '{}') : {};
    const msg = (key, fallback) => i18n[key] || fallback;

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
        { key: 'pull', label: msg('stepPull', 'Download / pull'), state: 'active' },
        { key: 'stop', label: msg('stepStop', 'Stop services'), state: 'pending' },
        { key: 'restart', label: msg('stepRestart', 'Docker restart'), state: 'pending' },
        { key: 'containers', label: msg('stepContainers', 'Container checks'), state: 'pending' },
        { key: 'app', label: msg('stepApp', 'Application check'), state: 'pending' },
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
        const prefix = isError ? msg('errorPrefix', 'ERROR: ') : '';
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
                const response = await fetch('/admin/version/update/runtime-status?complete=1', {
                    headers: { 'Accept': 'application/json' },
                    cache: 'no-store',
                });
                if (!response.ok) throw new Error(msg('runtimeUnavailable', 'runtime unavailable'));
                const payload = await response.json();
                if (!payload.ok) throw new Error(payload.error || msg('runtimeUnavailable', 'runtime unavailable'));
                const system = payload.system || {};
                const runtime = payload.runtime || {};
                if (runtime.ready) {
                    appendLog(msg('appAvailable', 'Application available.'));
                    window.adminSystemLock?.hide();
                    await refreshStatus(false);
                    return true;
                } else if (system.active) {
                    window.adminSystemLock?.refresh();
                }
            } catch {
                window.adminSystemLock?.showConnecting();
            }
            await sleep(2000);
        }
        appendLog(msg('restartTimeoutLog', 'The restart is taking too long. Check Docker, then run another check.'), true);
        renderStatus({
            ...currentStatus,
            status: 'error',
            status_label: msg('restartTimeoutLabel', 'Restart timeout'),
            status_tone: 'danger',
            reason: msg('restartTimeoutReason', 'The containers or application did not come back within the expected time.'),
            can_apply: false,
        });
        return false;
    }

    function renderStatus(status) {
        currentStatus = status || {};
        stateBox.dataset.tone = currentStatus.status_tone || 'warning';
        label.textContent = currentStatus.status_label || msg('unknownStatus', 'Unknown status');
        reason.textContent = currentStatus.reason || (
            currentStatus.status === 'update_available'
                ? msg('updateRequiresConfirm', 'Confirmation is required before applying.')
                : msg('noAutoAction', 'No automatic action will be started.')
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
            title.textContent = item.label || item.key || msg('checkFallback', 'Check');
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
                throw new Error(payload.error || msg('checkFailed', 'Unable to check.'));
            }
            renderStatus(payload.status);
        } catch (error) {
            appendLog(error?.message || msg('checkFailed', 'Unable to check.'), true);
            renderStatus({
                status: 'error',
                status_label: msg('errorLabel', 'Error'),
                status_tone: 'danger',
                reason: error?.message || msg('checkFailed', 'Unable to check.'),
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
                let errorMessage = msg('actionUnavailable', 'Action unavailable.');
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
                        appendLog(payload.message || msg('actionFailed', 'Action failed.'), true);
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
                    status_label: msg('errorLabel', 'Error'),
                    status_tone: 'danger',
                    reason: msg('updateFailedReason', 'The update did not complete. Check the logs below.'),
                    can_apply: false,
                });
            } else if (finalStatus) {
                renderStatus(finalStatus);
                appendLog(msg('done', 'Done.'));
                window.adminSystemLock?.refresh();
                if (finalStatus.status === 'restart_scheduled') {
                    pollRuntimeStatus();
                }
            }
        } catch (error) {
            appendLog(error?.message || msg('actionFailed', 'Action failed.'), true);
            window.adminSystemLock?.refresh();
            renderStatus({
                ...currentStatus,
                status: 'error',
                status_label: msg('errorLabel', 'Error'),
                status_tone: 'danger',
                reason: error?.message || msg('actionFailed', 'Action failed.'),
                can_apply: false,
            });
        } finally {
            setBusy(false);
        }
    }

    checkBtn.addEventListener('click', () => refreshStatus(true));
    applyBtn.addEventListener('click', async () => {
        if (!await window.appUI.confirm({
            titleText: msg('applyConfirmTitle', 'Apply update'),
            messageText: msg('applyConfirmMessage', 'Apply the displayed server update now?'),
            tone: 'warning',
            confirmLabel: msg('applyLabel', 'Apply'),
        })) return;
        streamAction('/admin/version/update/apply-stream', msg('applyStart', 'Applying update...'));
    });
    restartBtn.addEventListener('click', async () => {
        if (!await window.appUI.confirm({
            titleText: msg('restartConfirmTitle', 'Restart Docker'),
            messageText: msg('restartConfirmMessage', 'Restart the Docker stack now?'),
            tone: 'warning',
            confirmLabel: msg('restartLabel', 'Restart Docker'),
        })) return;
        streamAction('/admin/version/update/restart-stream', msg('restartStart', 'Restarting Docker stack...'));
    });

    renderStatus(currentStatus);
})();
