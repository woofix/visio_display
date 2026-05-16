# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

SETTINGS_SECTION_ALIASES = {
    "events": "meteo",
    "event": "meteo",
    "evenements": "meteo",
    "install": "installation",
    "installer": "installation",
    "superadmin": "administration",
    "alerte-prioritaire": "priority-alert",
    "alert": "priority-alert",
    "comptes-permissions": "accounts",
    "users": "accounts",
    "utilisateurs": "accounts",
    "ajouter-compte": "add-account",
    "gestion-ecrans": "screens",
    "mot-de-passe": "password",
    "backup": "sauvegardes",
    "backups": "sauvegardes",
    "fonctionnalites": "features",
    "features": "features",
    "nettoyage": "cleanup",
    "nettoyage-medias": "cleanup",
    "media-cleanup": "cleanup",
    "cleanup": "cleanup",
}

SETTINGS_SECTION_SLUGS = {
    "logo": "logo",
    "admins": "admins",
    "password": "mot-de-passe",
    "administration": "administration",
    "priority-alert": "alerte-prioritaire",
    "accounts": "comptes-permissions",
    "add-account": "ajouter-compte",
    "screens": "gestion-ecrans",
    "theme": "theme",
    "application": "application",
    "meteo": "meteo",
    "language": "language",
    "installation": "installation",
    "sauvegardes": "sauvegardes",
    "features": "fonctionnalites",
    "cleanup": "nettoyage-medias",
}

SETTINGS_SECTION_TEMPLATES = {
    "logo": "admin_settings_logo.html",
    "admins": "admin_settings_admins.html",
    "password": "admin_settings_password.html",
    "administration": "admin_settings_accounts.html",
    "priority-alert": "admin_settings_priority_alert.html",
    "accounts": "admin_settings_accounts.html",
    "add-account": "admin_settings_add_account.html",
    "screens": "admin_settings_screens.html",
    "theme": "admin_settings_theme.html",
    "application": "admin_settings_application.html",
    "meteo": "admin_settings_meteo.html",
    "language": "admin_settings_language.html",
    "installation": "admin_settings_installation.html",
    "sauvegardes": "admin_settings_backups.html",
    "features": "admin_settings_features.html",
    "cleanup": "admin_media_cleanup.html",
}

SUPERADMIN_SETTING_TABS = {
    "installation",
    "sauvegardes",
    "administration",
    "priority-alert",
    "accounts",
    "add-account",
    "screens",
    "features",
    "meteo",
}

_ICONS = {
    "activity": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>',
    "theme": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><circle cx="12" cy="12" r="10"/><path d="M12 2a10 10 0 0 1 0 20"/><path d="M2 12h10"/></svg>',
    "language": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    "password": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
    "logo": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>',
    "application": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>',
    "accounts": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    "roles": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>',
    "add-account": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>',
    "screens": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>',
    "meteo": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9z"/></svg>',
    "priority-alert": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    "features": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
    "installation": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
    "backups": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="3" x2="12" y2="15"/><path d="M5 7h14"/></svg>',
    "version": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>',
    "cleanup": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="u-icon-13"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>',
}

SETTINGS_NAV_GROUPS = (
    {
        "label_key": None,
        "items": (
            {
                "key": "activity",
                "href": "/admin/activity",
                "label_key": "nav_activity",
                "icon": _ICONS["activity"],
                "active_paths": ("/admin/activity",),
            },
        ),
    },
    {
        "label_key": "nav_label_account",
        "items": (
            {
                "key": "theme",
                "href": "/admin/settings/theme",
                "label_key": "nav_theme",
                "icon": _ICONS["theme"],
                "settings_active_paths": ("/admin/settings/theme",),
            },
            {
                "key": "language",
                "href": "/admin/settings/language",
                "label_key": "tab_language",
                "icon": _ICONS["language"],
                "settings_active_paths": ("/admin/settings/language",),
            },
            {
                "key": "password",
                "href": "/admin/settings/mot-de-passe",
                "label_key": "admins_change_password",
                "icon": _ICONS["password"],
                "settings_active_paths": ("/admin/settings/mot-de-passe",),
            },
        ),
    },
    {
        "label_key": "nav_label_appearance",
        "items": (
            {
                "key": "logo",
                "href": "/admin/settings/logo",
                "label_key": "nav_logo",
                "icon": _ICONS["logo"],
                "settings_active_paths": ("/admin/settings", "/admin/settings/logo"),
            },
            {
                "key": "application",
                "href": "/admin/settings/application",
                "label_key": "nav_application",
                "icon": _ICONS["application"],
                "settings_active_paths": ("/admin/settings/application",),
            },
        ),
    },
    {
        "label_key": "nav_label_administration",
        "superadmin_only": True,
        "items": (
            {
                "key": "accounts",
                "href": "/admin/settings/comptes-permissions",
                "label_key": "superadmin_accounts_perms",
                "icon": _ICONS["accounts"],
                "settings_active_paths": ("/admin/settings/administration", "/admin/settings/comptes-permissions"),
            },
            {
                "key": "roles",
                "href": "/admin/roles",
                "label_key": "nav_roles",
                "icon": _ICONS["roles"],
                "active_prefixes": ("/admin/roles",),
            },
            {
                "key": "add-account",
                "href": "/admin/settings/ajouter-compte",
                "label_key": "superadmin_add_account",
                "icon": _ICONS["add-account"],
                "settings_active_paths": ("/admin/settings/ajouter-compte",),
            },
            {
                "key": "screens",
                "href": "/admin/settings/gestion-ecrans",
                "label_key": "superadmin_screens_manage",
                "icon": _ICONS["screens"],
                "settings_active_paths": ("/admin/settings/gestion-ecrans",),
            },
            {
                "key": "meteo",
                "href": "/admin/settings/meteo",
                "label_key": "tab_meteo",
                "icon": _ICONS["meteo"],
                "settings_active_paths": ("/admin/settings/meteo",),
            },
            {
                "key": "priority-alert",
                "href": "/admin/settings/alerte-prioritaire",
                "label_key": "superadmin_priority_alert_title",
                "icon": _ICONS["priority-alert"],
                "settings_active_paths": ("/admin/settings/alerte-prioritaire",),
            },
            {
                "key": "features",
                "href": "/admin/settings/fonctionnalites",
                "label_key": "nav_features",
                "icon": _ICONS["features"],
                "settings_active_paths": ("/admin/settings/fonctionnalites",),
            },
        ),
    },
    {
        "label_key": "nav_label_system",
        "items": (
            {
                "key": "cleanup",
                "href": "/admin/settings/nettoyage-medias",
                "label_key": "nav_media_cleanup",
                "icon": _ICONS["cleanup"],
                "required_permission": "cleanup",
                "settings_active_paths": ("/admin/settings/nettoyage-medias",),
            },
            {
                "key": "installation",
                "href": "/admin/settings/installation",
                "label_key": "nav_installation",
                "icon": _ICONS["installation"],
                "superadmin_only": True,
                "settings_active_paths": ("/admin/settings/installation",),
            },
            {
                "key": "backups",
                "href": "/admin/settings/sauvegardes",
                "label_key": "nav_backups",
                "icon": _ICONS["backups"],
                "superadmin_only": True,
                "settings_active_paths": ("/admin/settings/sauvegardes",),
            },
            {
                "key": "version",
                "href": "/admin/version",
                "label_key": "nav_version",
                "icon": _ICONS["version"],
                "superadmin_only": True,
                "active_paths": ("/admin/version",),
            },
        ),
    },
)


def normalize_settings_tab(raw_tab):
    tab = (raw_tab or "logo").strip().lower()
    return SETTINGS_SECTION_ALIASES.get(tab, tab)


def settings_section_url(tab):
    tab = normalize_settings_tab(tab)
    return f"/admin/settings/{SETTINGS_SECTION_SLUGS.get(tab, 'logo')}"


def settings_section_template(tab):
    tab = normalize_settings_tab(tab)
    return SETTINGS_SECTION_TEMPLATES.get(tab, "admin_settings_logo.html")


def is_superadmin_settings_tab(tab):
    return normalize_settings_tab(tab) in SUPERADMIN_SETTING_TABS


def superadmin_nav_prefixes():
    prefixes = []
    for group in SETTINGS_NAV_GROUPS:
        if group.get("superadmin_only"):
            prefixes.extend(item["href"] for item in group["items"])
            continue
        prefixes.extend(item["href"] for item in group["items"] if item.get("superadmin_only"))
    prefixes.append("/admin/settings/administration")
    return tuple(prefixes)


def _normalize_path(path):
    return path[:-1] if path != "/" and path.endswith("/") else path


def _item_is_active(item, path, settings_path):
    if path in item.get("active_paths", ()):
        return True
    if settings_path in item.get("settings_active_paths", ()):
        return True
    return any(path.startswith(prefix) for prefix in item.get("active_prefixes", ()))


def settings_nav_groups(path, *, superadmin=False, permissions=None):
    path = path or ""
    settings_path = _normalize_path(path)
    permissions = set(permissions or ())
    groups = []
    for group in SETTINGS_NAV_GROUPS:
        if group.get("superadmin_only") and not superadmin:
            continue
        items = []
        for item in group["items"]:
            if item.get("superadmin_only") and not superadmin:
                continue
            required_permission = item.get("required_permission")
            if required_permission and not (superadmin or required_permission in permissions):
                continue
            items.append({**item, "active": _item_is_active(item, path, settings_path)})
        if items:
            groups.append({
                "label_key": group.get("label_key"),
                "items": items,
            })
    return groups


def is_settings_nav_path(path):
    path = path or ""
    if path.startswith("/admin/settings"):
        return True
    if path in {"/admin/superadmin", "/admin/features", "/admin/activity", "/admin/version"}:
        return True
    return path.startswith("/admin/roles")
