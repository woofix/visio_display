    const DEFAULT_DURATION = 15000;
    const FADE_DURATION    = 1500;
    const displayConfigEl = document.getElementById('display-config');
    const displayConfig = displayConfigEl ? JSON.parse(displayConfigEl.textContent || '{}') : {};
    const DEFAULT_SCREEN_NAME = displayConfig.defaultScreenName || '';
    const DISPLAY_API_TOKEN = displayConfig.displayApiToken || '';
    const SCREEN           = new URLSearchParams(location.search).get('screen') || '';
    const PERF_ENABLED = new URLSearchParams(location.search).get('perf') === '1';

    if (PERF_ENABLED) {
        const originalFetch = window.fetch.bind(window);
        window.fetch = function(resource, init) {
            const startedAt = performance.now();
            const label = typeof resource === 'string' ? resource : resource?.url || String(resource);
            return originalFetch(resource, init).then(response => {
                const elapsed = Math.round(performance.now() - startedAt);
                if (elapsed >= 500) {
                    console.warn('[Visio display perf] slow fetch', elapsed + 'ms', label, response.status);
                }
                return response;
            });
        };
        window.addEventListener('load', () => {
            const nav = performance.getEntriesByType('navigation')[0];
            console.info('[Visio display perf] page', {
                load: nav ? Math.round(nav.loadEventEnd) : null,
                transferSize: nav?.transferSize || 0,
            });
        });
    }

    function displayApiUrl(path, extraParams = {}) {
        const params = new URLSearchParams();
        if (SCREEN) params.set('screen', SCREEN);
        params.set('screen_token', DISPLAY_API_TOKEN);
        Object.entries(extraParams).forEach(([key, value]) => {
            if (value !== undefined && value !== null && value !== '') {
                params.set(key, value);
            }
        });
        return `${path}?${params.toString()}`;
    }

    function displayPageUrl(screen = '') {
        const params = new URLSearchParams();
        if (screen) params.set('screen', screen);
        params.set('screen_token', DISPLAY_API_TOKEN);
        return `/?${params.toString()}`;
    }

    function getDisplayBounds() {
        const dpr = Math.max(1, Math.min(window.devicePixelRatio || 1, 2));
        const viewport = window.visualViewport;
        const width = viewport?.width || window.innerWidth || document.documentElement.clientWidth || 0;
        const height = viewport?.height || window.innerHeight || document.documentElement.clientHeight || 0;
        return {
            width: Math.max(1, Math.round(width * dpr)),
            height: Math.max(1, Math.round(height * dpr)),
        };
    }

    function mediaApiUrl() {
        const bounds = getDisplayBounds();
        return displayApiUrl('/api/images', { w: bounds.width, h: bounds.height });
    }

    let media        = [];
    let durations    = {};
    let groupPools   = {};
    let sampledMedia = [];
    let currentIndex = 0;
    let currentSlide = null;
    let currentItem  = null;
    let timer        = null;
    let alertMessage = '';
    let alertPoller  = null;
    let mediaRefreshTimer = null;
    let haloRefreshTimer = null;
    let wakeLock     = null;
    let isAdvancingAfterMediaError = false;
    let mediaRefreshChannel = null;
    let mediaSignature = '';
    let poolSignature = '';

    const alertBox = document.getElementById('priority-alert');
    const alertText = document.getElementById('priority-alert-message');

    async function fetchMedia() {
        try {
            const res = await fetch(mediaApiUrl(), { cache: 'no-store' });
            if (!res.ok) return media.length ? media : [];
            const fetched = await res.json();
            return fetched.length ? fetched : [];
        } catch (e) {
            return media.length ? media : [];
        }
    }

    async function fetchPools() {
        try {
            const res = await fetch(displayApiUrl('/api/pools'), { cache: 'no-store' });
            if (!res.ok) return {};
            return await res.json();
        } catch (e) {
            return {};
        }
    }

    async function fetchHalo() {
        try {
            const res = await fetch(displayApiUrl('/api/halo'), { cache: 'no-store' });
            if (!res.ok) return null;
            return await res.json();
        } catch (e) {
            return null;
        }
    }

    function applyHalo(halo) {
        if (!halo?.rgb) return;
        document.documentElement.style.setProperty('--media-halo-rgb', halo.rgb);
        document.body?.style.setProperty('--media-halo-rgb', halo.rgb);
    }

    async function refreshHalo() {
        const halo = await fetchHalo();
        if (!halo) return;
        applyHalo(halo);
    }

    function getFilename(path) {
        return path.split('/').pop().split('?')[0];
    }

    function computeMediaSignature(items) {
        return items
            .map(item => `${item.path}|${item.type}|${item.rev || 0}|${(item.groups || []).slice().sort().join(',')}`)
            .sort()
            .join('||');
    }

    function mediaUrl(item) {
        const sep = item.path.includes('?') ? '&' : '?';
        return `${item.path}${sep}v=${encodeURIComponent(item?.rev || Date.now())}`;
    }

    function computePoolSignature(pools) {
        return JSON.stringify(
            Object.entries(pools)
                .sort(([a], [b]) => a.localeCompare(b))
        );
    }

    function samplePools(mediaList, pools) {
        if (!Object.keys(pools).length) return mediaList;
        const pooledGroups = new Set(Object.keys(pools));
        const groupSamples = {};
        for (const [group, size] of Object.entries(pools)) {
            const groupItems = mediaList.filter(item => (item.groups || []).includes(group));
            const shuffled = [...groupItems];
            for (let i = shuffled.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
            }
            groupSamples[group] = new Set(shuffled.slice(0, size).map(item => getFilename(item.path)));
        }
        const result = [];
        const seen = new Set();
        for (const item of mediaList) {
            const fname = getFilename(item.path);
            if (seen.has(fname)) continue;
            seen.add(fname);
            const itemPooledGroups = (item.groups || []).filter(g => pooledGroups.has(g));
            if (itemPooledGroups.length === 0 || itemPooledGroups.some(g => groupSamples[g].has(fname))) {
                result.push(item);
            }
        }
        return result.length ? result : mediaList;
    }

    async function fetchDurations() {
        try {
            const res = await fetch(displayApiUrl('/api/durations'), { cache: 'no-store' });
            if (!res.ok) return {};
            return await res.json();
        } catch (e) {
            return {};
        }
    }

    async function fetchPriorityAlert() {
        try {
            const res = await fetch(displayApiUrl('/api/priority-alert'), { cache: 'no-store' });
            if (!res.ok) return alertMessage;
            const data = await res.json();
            return (data.message || '').trim();
        } catch (e) {
            return alertMessage;
        }
    }

    async function requestWakeLock() {
        if (!('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            wakeLock.addEventListener('release', () => {
                wakeLock = null;
            }, { once: true });
        } catch (e) {
            wakeLock = null;
        }
    }

    function renderPriorityAlert(message) {
        if (!alertBox || !alertText) return;
        if (!message) {
            alertMessage = '';
            alertText.textContent = '';
            alertBox.classList.remove('visible');
            return;
        }
        if (message === alertMessage) return;
        alertMessage = message;
        alertText.textContent = message;
        alertBox.classList.add('visible');
    }

    async function refreshPriorityAlert() {
        const message = await fetchPriorityAlert();
        if (!message && alertMessage) {
            renderPriorityAlert('');
            return;
        }
        renderPriorityAlert(message);
    }

    function getDuration(item) {
        const filename = item.name || item.path.split('/').pop().split('?')[0];
        const d = durations[filename];
        return d ? d * 1000 : DEFAULT_DURATION;
    }

    function discardCurrentSlide(slide) {
        if (!slide || !slide.parentNode) return;
        if (slide === currentSlide) {
            currentSlide = null;
            currentItem = null;
        }
        slide.remove();
    }

    function scheduleAdvance(item, el) {
        const duration = getDuration(item);

        if (item.type === 'video') {
            let done = false;
            const advance = () => {
                if (done) return;
                done = true;
                next();
            };
            el.addEventListener('ended', advance, { once: true });
            timer = setTimeout(advance, duration);
        } else {
            timer = setTimeout(next, duration);
        }
    }

    function restartCurrentSlide(item) {
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
        const el = showSlide(item);
        scheduleAdvance(item, el);
    }

    async function handleMediaLoadError(item, slide) {
        const failedPath = item?.path || '';
        media = media.filter(candidate => candidate.path !== failedPath);
        sampledMedia = sampledMedia.filter(candidate => candidate.path !== failedPath);
        discardCurrentSlide(slide);

        try {
            await refreshMediaState();
        } catch (e) {
            // Keep the current in-memory fallback if the refresh also fails.
        }

        if (isAdvancingAfterMediaError) return;
        isAdvancingAfterMediaError = true;
        Promise.resolve().then(() => next()).finally(() => {
            isAdvancingAfterMediaError = false;
        });
    }

    function showSlide(item) {
        const slide = document.createElement('div');
        slide.className = 'slide';

        let el;
        if (item.type === 'video') {
            el = document.createElement('video');
            el.src         = mediaUrl(item);
            el.autoplay    = true;
            el.muted       = true;
            el.controls    = false;
            el.playsInline = true;
        } else {
            el = document.createElement('img');
            el.src = mediaUrl(item);
            el.alt = '';
        }

        slide.appendChild(el);
        document.body.appendChild(slide);

        const onLoadError = () => {
            console.warn('Media unavailable, skipping:', item.path);
            handleMediaLoadError(item, slide);
        };

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                slide.classList.add('active');
            });
        });

        if (currentSlide) {
            const old = currentSlide;
            const oldVid = old.querySelector('video');
            if (oldVid) oldVid.pause();
            old.classList.add('leaving');
            old.classList.remove('active');
            setTimeout(() => {
                if (old.parentNode) old.parentNode.removeChild(old);
            }, FADE_DURATION + 100);
        }

        currentSlide = slide;
        currentItem = item;
        if (item.type === 'video') {
            ['error', 'stalled', 'abort'].forEach(evt => {
                el.addEventListener(evt, onLoadError, { once: true });
            });
        } else {
            el.addEventListener('error', onLoadError, { once: true });
        }
        return el;
    }

    async function refreshMediaState() {
        const [freshMedia, freshDurations, freshPools] = await Promise.all([
            fetchMedia(), fetchDurations(), fetchPools()
        ]);
        durations  = freshDurations;
        groupPools = freshPools;
        if (!freshMedia.length) return;
        const nextMediaSignature = computeMediaSignature(freshMedia);
        const nextPoolSignature = computePoolSignature(groupPools);
        const mediaChanged = nextMediaSignature !== mediaSignature;
        const poolsChanged = nextPoolSignature !== poolSignature;

        if (mediaChanged || poolsChanged || currentIndex === 0 || !sampledMedia.length) {
            sampledMedia = samplePools(freshMedia, groupPools);
            mediaSignature = nextMediaSignature;
            poolSignature = nextPoolSignature;
        }
        media = sampledMedia.length ? sampledMedia : freshMedia;
        if (currentIndex >= media.length) currentIndex = 0;
        if (currentItem) {
            const updatedCurrentItem = media.find(item => item.path === currentItem.path);
            if (updatedCurrentItem && (updatedCurrentItem.rev || 0) !== (currentItem.rev || 0)) {
                restartCurrentSlide(updatedCurrentItem);
            } else if (!updatedCurrentItem) {
                currentItem = null;
            }
        }
    }

    async function handleExternalMediaRefresh() {
        await refreshMediaState();
    }

    function setupMediaRefreshListeners() {
        window.addEventListener('storage', event => {
            if (event.key === 'visio-display:media-refresh') {
                handleExternalMediaRefresh();
            }
        });

        if (!('BroadcastChannel' in window)) return;
        mediaRefreshChannel = new BroadcastChannel('visio-display-media');
        mediaRefreshChannel.addEventListener('message', event => {
            if (event?.data?.type === 'media-refresh') {
                handleExternalMediaRefresh();
            }
        });
    }

    async function next() {
        if (timer) { clearTimeout(timer); timer = null; }

        if (!media.length) {
            timer = setTimeout(next, 5000);
            return;
        }

        const item = media[currentIndex];
        currentIndex = (currentIndex + 1) % media.length;

        const el = showSlide(item);
        scheduleAdvance(item, el);
    }

    async function start() {
        await requestWakeLock();
        setupMediaRefreshListeners();
        await refreshHalo();
        await refreshMediaState();
        await refreshPriorityAlert();
        alertPoller = setInterval(refreshPriorityAlert, 5000);
        haloRefreshTimer = setInterval(refreshHalo, 5000);
        mediaRefreshTimer = setInterval(refreshMediaState, 15000);
        next();
    }

    start();

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            requestWakeLock();
        }
    });

    /* ── Screen switcher ── */
    (function() {
        const switcher = document.getElementById('screen-switcher');
        let hideTimer = null;

        function showSwitcher() {
            switcher.classList.add('sw-visible');
            clearTimeout(hideTimer);
            hideTimer = setTimeout(() => switcher.classList.remove('sw-visible'), 3000);
        }

        async function buildSwitcher() {
            try {
                const res = await fetch(displayApiUrl('/api/screens'), { cache: 'no-store' });
                if (!res.ok) return;
                const screens = await res.json();
                if (!screens.length) { switcher.remove(); return; }

                ['', ...screens].forEach(s => {
                    const btn = document.createElement('button');
                    btn.className = 'screen-btn' + (s === SCREEN ? ' active' : '');
                    btn.textContent = s || DEFAULT_SCREEN_NAME;
                    btn.addEventListener('click', () => {
                        window.location.href = displayPageUrl(s);
                    });
                    switcher.appendChild(btn);
                });

                /* Briefly appears on load, then hides */
                showSwitcher();
                /* Reappears on mouse movement or touch */
                document.addEventListener('mousemove', showSwitcher);
                document.addEventListener('touchstart', showSwitcher);
            } catch(e) { switcher.remove(); }
        }

        buildSwitcher();
    })();
