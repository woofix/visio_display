const adminActivityConfigEl = document.getElementById('admin-activity-config');
const adminActivityConfig = adminActivityConfigEl ? JSON.parse(adminActivityConfigEl.textContent || '{}') : {};
function resetActivityFilters() {
    document.getElementById('filter-search').value = '';
    document.getElementById('filter-user').value = '';
    document.getElementById('filter-action').value = '';
    document.getElementById('filter-date-from').value = '';
    document.getElementById('filter-date-to').value = '';
    document.getElementById('filter-sort').value = 'date_desc';
    applyFilters();
}

function applyFilters() {
    const search = document.getElementById('filter-search').value.toLowerCase().trim();
    const action = document.getElementById('filter-action').value;
    const user = document.getElementById('filter-user').value;
    const dateFrom = document.getElementById('filter-date-from').value;
    const dateTo = document.getElementById('filter-date-to').value;
    const sort = document.getElementById('filter-sort').value;
    const tbody = document.getElementById('log-body');
    const rows = Array.from(tbody.querySelectorAll('tr[data-action]'));

    let visible = 0;
    rows.forEach((row) => {
        const rowDate = row.dataset.date || '';
        const matchSearch = !search || row.dataset.search.includes(search);
        const matchAction = !action || row.dataset.action === action;
        const matchUser = !user || row.dataset.user === user;
        const matchFrom = !dateFrom || rowDate >= dateFrom;
        const matchTo = !dateTo || rowDate <= dateTo;
        const show = matchSearch && matchAction && matchUser && matchFrom && matchTo;
        row.style.display = show ? '' : 'none';
        if (show) visible += 1;
    });

    const collator = new Intl.Collator('fr', { sensitivity: 'base' });
    rows.sort((a, b) => {
        if (sort === 'date_asc') return a.dataset.timestamp.localeCompare(b.dataset.timestamp);
        if (sort === 'date_desc') return b.dataset.timestamp.localeCompare(a.dataset.timestamp);
        if (sort === 'user_asc') return collator.compare(a.dataset.user, b.dataset.user) || b.dataset.timestamp.localeCompare(a.dataset.timestamp);
        if (sort === 'user_desc') return collator.compare(b.dataset.user, a.dataset.user) || b.dataset.timestamp.localeCompare(a.dataset.timestamp);
        if (sort === 'action_asc') return collator.compare(a.dataset.action, b.dataset.action) || b.dataset.timestamp.localeCompare(a.dataset.timestamp);
        if (sort === 'action_desc') return collator.compare(b.dataset.action, a.dataset.action) || b.dataset.timestamp.localeCompare(a.dataset.timestamp);
        return 0;
    });
    rows.forEach((row) => tbody.appendChild(row));

    const countEl = document.getElementById('log-count');
    if (countEl) countEl.textContent = `${visible} / ${rows.length} ${adminActivityConfig.visibleCountSuffix || ''}`;
}

applyFilters();
