const adminLayoutConfigEl = document.getElementById('admin-layout-config');
const adminLayoutConfig = adminLayoutConfigEl ? JSON.parse(adminLayoutConfigEl.textContent || '{}') : {};
window.ADMIN_LAYOUT_CONFIG = adminLayoutConfig;
window.CSRF_TOKEN = adminLayoutConfig.csrfToken || '';

(function() {
    const root = document.documentElement;

    function resolveTheme(preference) {
        return ['violet', 'bleu', 'sombre'].includes(preference) ? preference : 'violet';
    }

    function applyThemePreference(preference) {
        root.dataset.themePreference = preference || 'violet';
        root.dataset.theme = resolveTheme(root.dataset.themePreference);
    }

    window.applyThemePreference = applyThemePreference;
    applyThemePreference(root.dataset.themePreference);
})();

window.__flashMessages = adminLayoutConfig.flashMessages || [];

(function() {
    const perfParams = new URLSearchParams(window.location.search);
    const perfEnabled = perfParams.get('perf') === '1' || window.localStorage?.getItem('visioPerf') === '1';

    if (perfParams.get('perf') === '1') {
        try { window.localStorage.setItem('visioPerf', '1'); } catch {}
    }

    if (perfEnabled && 'PerformanceObserver' in window) {
        try {
            const slowResources = [];
            const resourceObserver = new PerformanceObserver(list => {
                list.getEntries().forEach(entry => {
                    if (entry.duration >= 500 || entry.transferSize >= 120000) {
                        slowResources.push({
                            name: entry.name,
                            type: entry.initiatorType,
                            duration: Math.round(entry.duration),
                            transferSize: entry.transferSize || 0,
                            decodedBodySize: entry.decodedBodySize || 0,
                        });
                    }
                });
            });
            resourceObserver.observe({ type: 'resource', buffered: true });

            const longTaskObserver = new PerformanceObserver(list => {
                list.getEntries().forEach(entry => {
                    console.warn('[Visio perf] long task', Math.round(entry.duration) + 'ms');
                });
            });
            longTaskObserver.observe({ type: 'longtask', buffered: true });

            window.addEventListener('load', () => {
                setTimeout(() => {
                    const nav = performance.getEntriesByType('navigation')[0];
                    console.info('[Visio perf] page', {
                        path: location.pathname,
                        domContentLoaded: nav ? Math.round(nav.domContentLoadedEventEnd) : null,
                        load: nav ? Math.round(nav.loadEventEnd) : null,
                        transferSize: nav?.transferSize || 0,
                        slowResources,
                    });
                }, 0);
            });
        } catch {}
    }

    function isSameOrigin(resource) {
        const url = new URL(resource, window.location.href);
        return url.origin === window.location.origin;
    }

    function ensureCsrfField(form) {
        if (!form || form.querySelector('input[name="_csrf_token"]')) return;
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = '_csrf_token';
        input.value = window.CSRF_TOKEN;
        form.appendChild(input);
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[method="post"], form[method="POST"], form:not([method])').forEach(ensureCsrfField);
    });

    const originalFetch = window.fetch.bind(window);
    window.fetch = function(resource, init = {}) {
        const startedAt = perfEnabled ? performance.now() : 0;
        const resourceLabel = typeof resource === 'string' ? resource : resource?.url || String(resource);
        const method = (init.method || 'GET').toUpperCase();
        if (isSameOrigin(resource) && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
            const headers = new Headers(init.headers || {});
            headers.set('X-CSRF-Token', window.CSRF_TOKEN);
            init = { ...init, headers };
        }
        return originalFetch(resource, init).then(response => {
            if (perfEnabled) {
                const elapsed = Math.round(performance.now() - startedAt);
                if (elapsed >= 500) {
                    console.warn('[Visio perf] slow fetch', elapsed + 'ms', method, resourceLabel, response.status);
                }
            }
            return response;
        });
    };
})();
