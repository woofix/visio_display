# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import os

import requests


DEFAULT_TIMEOUT_SECONDS = 20
STREAM_TIMEOUT_SECONDS = 3600


class UpdaterClientError(RuntimeError):
    pass


def updater_configured():
    return bool(_base_url() and _token())


def _base_url():
    return os.environ.get("UPDATER_API_URL", "").strip().rstrip("/")


def _token():
    return os.environ.get("UPDATER_API_TOKEN", "").strip()


def _headers(accept="application/json"):
    token = _token()
    if not token:
        raise UpdaterClientError("UPDATER_API_TOKEN manquant.")
    return {
        "Accept": accept,
        "Authorization": f"Bearer {token}",
        "User-Agent": "visio-display-app-updater-client/1.0",
    }


def _url(path):
    base_url = _base_url()
    if not base_url:
        raise UpdaterClientError("UPDATER_API_URL manquant.")
    return f"{base_url}{path}"


def get_json(path, *, params=None, timeout=DEFAULT_TIMEOUT_SECONDS):
    try:
        response = requests.get(_url(path), headers=_headers(), params=params or {}, timeout=timeout)
    except requests.RequestException as exc:
        raise UpdaterClientError(f"Updater indisponible: {exc}") from exc
    return _parse_json_response(response)


def stream_operation(path, *, progress_callback=None, timeout=STREAM_TIMEOUT_SECONDS):
    try:
        with requests.post(
            _url(path),
            headers=_headers("application/x-ndjson"),
            timeout=timeout,
            stream=True,
        ) as response:
            if response.status_code >= 400:
                payload = _parse_json_response(response)
                raise UpdaterClientError(payload.get("error") or f"Updater HTTP {response.status_code}")
            final_status = None
            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise UpdaterClientError("Réponse updater invalide.") from exc
                event_type = payload.get("type")
                if event_type == "log" and progress_callback:
                    progress_callback(str(payload.get("message") or ""))
                elif event_type == "error":
                    raise UpdaterClientError(str(payload.get("message") or "Action updater échouée."))
                elif event_type == "done":
                    final_status = payload.get("status")
            if not isinstance(final_status, dict):
                raise UpdaterClientError("L'updater n'a pas renvoyé de statut final.")
            return final_status
    except requests.RequestException as exc:
        raise UpdaterClientError(f"Updater indisponible: {exc}") from exc


def _parse_json_response(response):
    try:
        payload = response.json()
    except ValueError as exc:
        raise UpdaterClientError(f"Réponse updater invalide: HTTP {response.status_code}") from exc
    if response.status_code >= 400 or not payload.get("ok", False):
        raise UpdaterClientError(payload.get("error") or f"Updater HTTP {response.status_code}")
    return payload
