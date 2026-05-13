const adminProgrammingConfigEl = document.getElementById('admin-programming-config');
const adminProgrammingConfig = adminProgrammingConfigEl ? JSON.parse(adminProgrammingConfigEl.textContent || '{}') : {};
const canSchedule = !!adminProgrammingConfig.canSchedule;
const programmingI18n = adminProgrammingConfig.labels || {};
const rowNodes = [...document.querySelectorAll('.programming-row')];
const calendarRows = [...document.querySelectorAll('.calendar-scope-row')];
const calendarEvents = [...document.querySelectorAll('.calendar-event')];

function normalize(text) {
    return (text || '').toLowerCase().trim();
}

function dateMatches(rowStart, rowEnd, filterStart, filterEnd) {
    if (filterStart && rowEnd && rowEnd < filterStart) return false;
    if (filterEnd && rowStart && rowStart > filterEnd) return false;
    return true;
}

function updateCalendarEmptyStates() {
    document.querySelectorAll('.calendar-cell').forEach(cell => {
        const visibleEvents = [...cell.querySelectorAll('.calendar-event')].filter(node => node.style.display !== 'none');
        const empty = cell.querySelector('.calendar-empty');
        if (empty) empty.style.display = visibleEvents.length ? 'none' : '';
    });
}

function applyProgrammingFilters() {
    const screen = document.getElementById('filter-screen').value;
    const group = normalize(document.getElementById('filter-group').value);
    const media = normalize(document.getElementById('filter-media').value);
    const dateStart = document.getElementById('filter-date-start').value;
    const dateEnd = document.getElementById('filter-date-end').value;
    let visibleCount = 0;

    rowNodes.forEach(row => {
        const rowScreen = row.dataset.screen || '';
        const rowGroups = normalize(row.dataset.groups).split('||').filter(Boolean);
        const rowFile = normalize(row.dataset.file);
        const rowStart = row.dataset.dateStart || '';
        const rowEnd = row.dataset.dateEnd || '';
        const screenMatch = !screen || (screen === '__global__' ? rowScreen === '' : rowScreen === screen);
        const groupMatch = !group || rowGroups.includes(group);
        const mediaMatch = !media || rowFile.includes(media);
        const rangeMatch = dateMatches(rowStart, rowEnd, dateStart, dateEnd);
        const visible = screenMatch && groupMatch && mediaMatch && rangeMatch;
        row.style.display = visible ? '' : 'none';
        if (visible) visibleCount += 1;
    });

    calendarRows.forEach(node => {
        const rowScreen = node.dataset.screen || '';
        node.style.display = (!screen || (screen === '__global__' ? rowScreen === '' : rowScreen === screen)) ? '' : 'none';
    });

    calendarEvents.forEach(node => {
        const eventScreen = node.dataset.screen || '';
        const eventGroups = normalize(node.dataset.groups).split('||').filter(Boolean);
        const eventFile = normalize(node.dataset.file);
        const eventDate = node.dataset.date || '';
        const screenMatch = !screen || (screen === '__global__' ? eventScreen === '' : eventScreen === screen);
        const groupMatch = !group || eventGroups.includes(group);
        const mediaMatch = !media || eventFile.includes(media);
        const dateMatch = (!dateStart || eventDate >= dateStart) && (!dateEnd || eventDate <= dateEnd);
        node.style.display = (screenMatch && groupMatch && mediaMatch && dateMatch) ? '' : 'none';
    });

    updateCalendarEmptyStates();
    document.getElementById('summary-visible').textContent = visibleCount;
    const empty = document.getElementById('list-empty-state');
    if (empty) empty.style.display = visibleCount ? 'none' : '';
}

['filter-screen', 'filter-group', 'filter-media', 'filter-date-start', 'filter-date-end'].forEach(id => {
    document.getElementById(id)?.addEventListener(id === 'filter-media' ? 'input' : 'change', applyProgrammingFilters);
});

document.getElementById('btn-reset-filters')?.addEventListener('click', () => {
    ['filter-screen', 'filter-group', 'filter-media', 'filter-date-start', 'filter-date-end'].forEach(id => {
        const field = document.getElementById(id);
        if (!field) return;
        field.value = '';
    });
    applyProgrammingFilters();
});

applyProgrammingFilters();

if (canSchedule) {
    const modal = document.getElementById('programming-modal');
    const modalTitle = document.getElementById('programming-modal-title');
    const filenameField = document.getElementById('programming-filename');
    const screenField = document.getElementById('programming-screen');
    const dateStartField = document.getElementById('programming-date-start');
    const dateEndField = document.getElementById('programming-date-end');
    const timeStartField = document.getElementById('programming-time-start');
    const timeEndField = document.getElementById('programming-time-end');
    const deleteBtn = document.getElementById('programming-delete-btn');
    const mediaSearch = document.getElementById('programming-media-search');
    const mediaGrid = document.getElementById('programming-media-grid');
    const mediaCountEl = document.getElementById('programming-media-count');
    const mediaErrorEl = document.getElementById('programming-media-error');
    const vignetteItems = [...document.querySelectorAll('#programming-media-grid .media-vignette-item')];
    let currentMode = 'create';
    let originalFilename = '';
    let originalScreen = '';

    function selectVignette(filename) {
        vignetteItems.forEach(item => {
            const isSelected = item.dataset.filename === filename;
            item.classList.toggle('selected', isSelected);
            item.setAttribute('aria-selected', isSelected ? 'true' : 'false');
        });
        filenameField.value = filename || '';
        if (filename) mediaErrorEl.classList.remove('visible');
    }

    function syncVignetteCount() {
        const visible = vignetteItems.filter(i => !i.classList.contains('hidden')).length;
        const template = visible > 1 ? programmingI18n.mediaCountPlural : programmingI18n.mediaCountSingular;
        mediaCountEl.textContent = template.replace('__count__', visible);
    }

    mediaSearch?.addEventListener('input', () => {
        const query = mediaSearch.value.trim().toLowerCase();
        vignetteItems.forEach(item => {
            item.classList.toggle('hidden', !!query && !item.dataset.name.includes(query));
        });
        syncVignetteCount();
    });

    vignetteItems.forEach(item => {
        item.addEventListener('click', () => selectVignette(item.dataset.filename));
        item.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectVignette(item.dataset.filename); }
        });
    });

    syncVignetteCount();

    function openModal(mode, payload = {}) {
        currentMode = mode;
        originalFilename = payload.originalFilename || payload.filename || '';
        originalScreen = payload.originalScreen || payload.screen || '';
        modalTitle.textContent = mode === 'edit' ? programmingI18n.editSlot : (mode === 'duplicate' ? programmingI18n.duplicateSlot : programmingI18n.newSlot);
        mediaSearch.value = '';
        vignetteItems.forEach(i => i.classList.remove('hidden'));
        syncVignetteCount();
        const target = payload.filename || vignetteItems[0]?.dataset.filename || '';
        selectVignette(target);
        const selected = vignetteItems.find(i => i.dataset.filename === target);
        if (selected) selected.scrollIntoView({ block: 'nearest' });
        screenField.value = payload.screen || '';
        dateStartField.value = payload.dateStart || '';
        dateEndField.value = payload.dateEnd || '';
        timeStartField.value = payload.timeStart || '';
        timeEndField.value = payload.timeEnd || '';
        deleteBtn.style.display = mode === 'edit' ? '' : 'none';
        mediaErrorEl.classList.remove('visible');
        modal.classList.add('open');
    }

    function closeModal() {
        modal.classList.remove('open');
    }

    document.getElementById('btn-create-programming')?.addEventListener('click', () => openModal('create'));
    document.getElementById('programming-modal-close').addEventListener('click', closeModal);
    document.getElementById('programming-cancel-btn').addEventListener('click', closeModal);
    modal.addEventListener('click', event => {
        if (event.target === modal) closeModal();
    });

    document.querySelectorAll('.btn-edit').forEach(button => {
        button.addEventListener('click', () => openModal('edit', {
            filename: button.dataset.filename,
            screen: button.dataset.screen,
            dateStart: button.dataset.dateStart,
            dateEnd: button.dataset.dateEnd,
            timeStart: button.dataset.timeStart,
            timeEnd: button.dataset.timeEnd,
        }));
    });

    document.querySelectorAll('.btn-duplicate').forEach(button => {
        button.addEventListener('click', () => openModal('duplicate', {
            filename: button.dataset.filename,
            screen: button.dataset.screen,
            dateStart: button.dataset.dateStart,
            dateEnd: button.dataset.dateEnd,
            timeStart: button.dataset.timeStart,
            timeEnd: button.dataset.timeEnd,
            originalFilename: button.dataset.filename,
            originalScreen: button.dataset.screen,
        }));
    });

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': window.CSRF_TOKEN,
            },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || programmingI18n.saveError);
        }
        return data;
    }

    document.getElementById('programming-save-btn').addEventListener('click', async () => {
        if (!filenameField.value) {
            mediaErrorEl.classList.add('visible');
            mediaGrid.scrollIntoView({ block: 'nearest' });
            return;
        }
        try {
            await postJson('/programming/save', {
                filename: filenameField.value,
                screen: screenField.value,
                date_start: dateStartField.value,
                date_end: dateEndField.value,
                time_start: timeStartField.value,
                time_end: timeEndField.value,
                original_filename: currentMode === 'create' ? filenameField.value : originalFilename,
                original_screen: currentMode === 'create' ? screenField.value : originalScreen,
            });
            window.location.reload();
        } catch (error) {
            await window.appUI.alert(error.message, {
                titleText: programmingI18n.saveErrorTitle,
                tone: 'error',
                confirmLabel: programmingI18n.closeLabel,
            });
        }
    });

    deleteBtn.addEventListener('click', async () => {
        if (!await window.appUI.confirm({
            titleText: programmingI18n.deleteTitle,
            messageText: programmingI18n.deleteConfirm,
            tone: 'error',
            confirmLabel: programmingI18n.deleteLabel,
        })) return;
        try {
            await postJson('/programming/delete', {
                filename: originalFilename,
                screen: originalScreen,
            });
            window.location.reload();
        } catch (error) {
            await window.appUI.alert(error.message, {
                titleText: programmingI18n.deleteErrorTitle,
                tone: 'error',
                confirmLabel: programmingI18n.closeLabel,
            });
        }
    });
}
