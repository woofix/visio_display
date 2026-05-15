# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os

from flask import url_for


ICON_ROOTS = (
    ("tabler-outline", "assets/tabler/outline"),
    ("tabler-filled", "assets/tabler/filled"),
    ("lucide", "assets/lucide"),
)


def scan_svg_icons(category=None, query="", limit=60, offset=0):
    query = str(query or "").strip().lower()
    category = str(category or "").strip()
    limit = max(1, min(120, int(limit or 60)))
    offset = max(0, int(offset or 0))
    static_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    icons = []

    for icon_category, rel_dir in ICON_ROOTS:
        if category and category != icon_category:
            continue
        abs_dir = os.path.join(static_root, rel_dir)
        if not os.path.isdir(abs_dir):
            continue
        for filename in sorted(os.listdir(abs_dir)):
            if not filename.lower().endswith(".svg"):
                continue
            name = os.path.splitext(filename)[0]
            if query and query not in name.lower():
                continue
            icons.append({
                "name": name,
                "category": icon_category,
                "url": url_for("static", filename=f"{rel_dir}/{filename}"),
            })

    return {
        "items": icons[offset:offset + limit],
        "total": len(icons),
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(icons),
    }
