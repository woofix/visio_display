# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import json
import logging
import os

import requests


DEFAULT_TIMEOUT_SECONDS = 20
STREAM_TIMEOUT_SECONDS = 3600
DEFAULT_DOCKER_UPDATER_URL = "http://updater:8090"
PUBLIC_UPDATER_UNAVAILABLE_MESSAGE = "Service de mise à jour temporairement indisponible. Réessayez plus tard."
LOGGER = logging.getLogger(__name__)


class UpdaterClientError(RuntimeError):
    pass


def updater_configured():
    return bool(_base_url() and _token())


def _base_url():
    configured = os.environ.get("UPDATER_API_URL", "").strip().rstrip("/")
    if configured:
        return configured
    if _running_in_container() and _token():
        return DEFAULT_DOCKER_UPDATER_URL
    return ""


def _token():
    configured = os.environ.get("UPDATER_API_TOKEN", "").strip()
    if configured:
        return configured
    return _dotenv_value("UPDATER_API_TOKEN")


def _running_in_container():
    return os.path.exists("/.dockerenv") or os.environ.get("container", "").strip() != ""


def _dotenv_value(key):
    for path in (os.path.join(os.getcwd(), ".env"), "/app/.env"):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, value = line.split("=", 1)
                    if name.strip() == key:
                        return value.strip().strip("'\"")
        except OSError:
            continue
    return ""


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
        LOGGER.warning("Updater request failed path=%s timeout=%s error=%r", path, timeout, exc)
        raise UpdaterClientError(PUBLIC_UPDATER_UNAVAILABLE_MESSAGE) from exc
    return _parse_json_response(response)


def stream_operation(path, *, progress_callback=None, payload=None, timeout=STREAM_TIMEOUT_SECONDS):
    try:
        with requests.post(
            _url(path),
            headers=_headers("application/x-ndjson"),
            json=payload or {},
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
        LOGGER.warning("Updater stream failed path=%s timeout=%s error=%r", path, timeout, exc)
        raise UpdaterClientError(PUBLIC_UPDATER_UNAVAILABLE_MESSAGE) from exc


def _parse_json_response(response):
    try:
        payload = response.json()
    except ValueError as exc:
        LOGGER.warning("Updater returned invalid JSON status=%s body=%r", response.status_code, getattr(response, "text", ""))
        raise UpdaterClientError(PUBLIC_UPDATER_UNAVAILABLE_MESSAGE) from exc
    if response.status_code >= 400 or not payload.get("ok", False):
        LOGGER.warning("Updater returned error status=%s payload=%r", response.status_code, payload)
        raise UpdaterClientError(payload.get("error") or PUBLIC_UPDATER_UNAVAILABLE_MESSAGE)
    return payload
