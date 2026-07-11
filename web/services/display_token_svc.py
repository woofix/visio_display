# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import os
import secrets

from flask import current_app, has_app_context


SCREEN_TOKEN_QUERY_PARAM = "screen_token"
SCREEN_TOKEN_HEADER = "X-Screen-Token"


def get_display_api_token():
    if has_app_context():
        configured = current_app.config.get("DISPLAY_API_TOKEN", "")
        if configured:
            return str(configured).strip()
    return os.environ.get("DISPLAY_API_TOKEN", "").strip()


def require_display_api_token():
    token = get_display_api_token()
    if not token:
        raise RuntimeError(
            "DISPLAY_API_TOKEN absent. Renseignez .env ou lancez scripts/security_bootstrap.sh install ."
        )
    return token


def screen_token_is_valid(request):
    expected = require_display_api_token()
    provided = (
        request.headers.get(SCREEN_TOKEN_HEADER)
        or request.args.get(SCREEN_TOKEN_QUERY_PARAM)
        or request.args.get("token")
        or ""
    )
    return bool(provided) and secrets.compare_digest(str(provided), expected)
