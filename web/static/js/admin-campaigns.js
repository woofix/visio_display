document.querySelectorAll('[data-campaign-toggle]').forEach((toggle) => {
    toggle.addEventListener('click', () => {
        toggle.closest('.campaign-card').classList.toggle('open');
    });
});

document.querySelectorAll('[data-media-picker]').forEach((picker) => {
    const search = picker.querySelector('[data-media-search]');
    const cards = Array.from(picker.querySelectorAll('[data-media-card]'));
    const count = picker.querySelector('[data-media-count]');
    const format = (template, values) => Object.entries(values).reduce(
        (result, [key, value]) => result.replaceAll(key, String(value)),
        template
    );

    const sync = () => {
        const query = (search?.value || '').trim().toLowerCase();
        let visible = 0;
        let selected = 0;

        cards.forEach((card) => {
            const checkbox = card.querySelector('[data-media-checkbox]');
            const matches = !query || card.dataset.mediaName.includes(query);
            card.classList.toggle('hidden', !matches);
            card.classList.toggle('selected', !!checkbox?.checked);
            if (matches) {
                visible += 1;
            }
            if (checkbox?.checked) {
                selected += 1;
            }
        });

        if (count) {
            count.textContent = selected
                ? format(
                    selected > 1 ? picker.dataset.selectedVisiblePlural : picker.dataset.selectedVisibleSingular,
                    {'__S__': selected, '__V__': visible}
                )
                : format(
                    visible > 1 ? picker.dataset.visiblePlural : picker.dataset.visibleSingular,
                    {'__N__': visible}
                );
        }
    };

    cards.forEach((card) => {
        const checkbox = card.querySelector('[data-media-checkbox]');
        checkbox?.addEventListener('change', sync);
    });
    search?.addEventListener('input', sync);
    sync();
});
