(function() {
    const panel = document.getElementById('server-update-panel');
    if (!panel) return;

    const checkBtn = document.getElementById('update-check-btn');
    const applyBtn = document.getElementById('update-apply-btn');
    const stateBox = document.getElementById('update-state');
    const label = document.getElementById('update-status-label');
    const reason = document.getElementById('update-status-reason');
    const checksBox = document.getElementById('update-checks');
    const confirmBox = document.getElementById('update-confirm');
    const logBox = document.getElementById('update-log');
    const progressOverlay = document.getElementById('update-progress-overlay');
    const progressTitle = document.getElementById('update-progress-title');
    const progressText = document.getElementById('update-progress-text');
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
    }

    function setUpdateProgress(isVisible, title, detail) {
        if (!progressOverlay) return;
        panel.dataset.updating = isVisible ? 'true' : 'false';
        progressOverlay.hidden = !isVisible;
        if (title && progressTitle) progressTitle.textContent = title;
        if (detail && progressText) progressText.textContent = detail;
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

    function reloadPageSoon() {
        setTimeout(() => {
            window.location.reload();
        }, 800);
    }

    function renderRestartScheduled(reason) {
        renderStatus({
            ...currentStatus,
            status: 'restart_scheduled',
            status_label: msg('restartScheduledLabel', 'Restart started'),
            status_tone: 'success',
            reason: reason || msg('restartScheduledReason', 'The Docker stack is restarting in the background.'),
            can_apply: false,
            can_restart: false,
        });
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
                appendLog(msg('appAvailable', 'Application available.'));
                appendLog(msg('restartReloading', 'Reloading page...'));
                setUpdateProgress(
                    true,
                    msg('updateReloadWaitTitle', 'Administration ready'),
                    msg('updateReloadWaitDesc', 'The page will reopen automatically.')
                );
                reloadPageSoon();
                return true;
            } catch {}
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
        setUpdateProgress(false);
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
        applyBtn.disabled = !canApply;
        applyBtn.style.display = canApply ? '' : 'none';
        applyBtn.setAttribute('aria-hidden', canApply ? 'false' : 'true');
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
        setUpdateProgress(
            true,
            msg('updateWaitTitle', 'Update in progress'),
            msg('updateWaitDesc', 'Please keep this page open. The administration will reopen automatically when ready.')
        );
        logBox.hidden = false;
        logBox.textContent = '';
        appendLog(startMessage);
        let finalStatus = null;
        let failed = false;
        let restartStarted = false;

        const restartSignals = [
            msg('restartProgress', 'Docker restart in progress...'),
            msg('restartBackground', 'The restart will continue in the background.'),
            msg('restartScheduledLabel', 'Restart started'),
        ].filter(Boolean);

        function noteRestartProgress(message) {
            const normalized = String(message || '').toLowerCase();
            const dockerComposeRestartStarted = (
                /^container\s+.+\s+recreat/.test(normalized)
                || normalized.includes('exporting to image')
                || normalized.includes('writing image sha256:')
                || normalized.includes('naming to docker.io/')
            );
            if (
                restartSignals.some(signal => signal && String(signal).toLowerCase() && normalized.includes(String(signal).toLowerCase()))
                || (normalized.includes('docker') && (normalized.includes('restart') || normalized.includes('redemarr') || normalized.includes('redémarr')))
                || dockerComposeRestartStarted
            ) {
                restartStarted = true;
            }
        }

        async function continueAfterRestartInterruption() {
            appendLog(msg('restartStreamInterrupted', 'Connection interrupted during restart. Checking application availability...'));
            renderRestartScheduled(msg('restartScheduledReason', 'The Docker stack is restarting in the background.'));
            setUpdateProgress(
                true,
                msg('updateRestartWaitTitle', 'Administration restarting'),
                msg('updateRestartWaitDesc', 'The update is applied. The administration is coming back online.')
            );
            setBusy(false);
            await pollRuntimeStatus();
        }

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
            const returnsBeforeConnectionClose = false;

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
                        noteRestartProgress(payload.message || '');
                    } else if (payload.type === 'error') {
                        failed = true;
                        appendLog(payload.message || msg('actionFailed', 'Action failed.'), true);
                    } else if (payload.type === 'done') {
                        finalStatus = payload.status;
                        if (finalStatus && finalStatus.status === 'restart_scheduled') {
                            restartStarted = true;
                        }
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
                setUpdateProgress(false);
            } else if (finalStatus) {
                renderStatus(finalStatus);
                appendLog(msg('done', 'Done.'));
                if (finalStatus.status === 'restart_scheduled') {
                    setUpdateProgress(
                        true,
                        msg('updateRestartWaitTitle', 'Administration restarting'),
                        msg('updateRestartWaitDesc', 'The update is applied. The administration is coming back online.')
                    );
                    await pollRuntimeStatus();
                } else {
                    setUpdateProgress(false);
                }
            } else if (restartStarted) {
                await continueAfterRestartInterruption();
            } else {
                throw new Error(msg('actionFailed', 'Action failed.'));
            }
        } catch (error) {
            if (!failed && (restartStarted || (finalStatus && finalStatus.status === 'restart_scheduled'))) {
                await continueAfterRestartInterruption();
                return;
            }
            appendLog(error?.message || msg('actionFailed', 'Action failed.'), true);
            renderStatus({
                ...currentStatus,
                status: 'error',
                status_label: msg('errorLabel', 'Error'),
                status_tone: 'danger',
                reason: error?.message || msg('actionFailed', 'Action failed.'),
                can_apply: false,
            });
            setUpdateProgress(false);
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

    renderStatus(currentStatus);
})();
