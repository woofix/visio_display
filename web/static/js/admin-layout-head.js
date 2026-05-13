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
        const method = (init.method || 'GET').toUpperCase();
        if (isSameOrigin(resource) && !['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
            const headers = new Headers(init.headers || {});
            headers.set('X-CSRF-Token', window.CSRF_TOKEN);
            init = { ...init, headers };
        }
        return originalFetch(resource, init);
    };
})();
