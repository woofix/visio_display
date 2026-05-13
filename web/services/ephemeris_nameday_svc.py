# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import contextlib
import json
import os
import re
import threading
import unicodedata
from datetime import datetime, timezone

import requests

from constants import PRIVATE_DATA_DIR
from services.media_svc import strip_html

NAMEDAY_CACHE_FILE = os.path.join(PRIVATE_DATA_DIR, "ephemeris_namedays.json")


def normalize_text(value):
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.casefold().strip()


def nameday_key(target_date):
    return f"{target_date.month:02d}-{target_date.day:02d}"


def load_nameday_cache():
    try:
        with open(NAMEDAY_CACHE_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_nameday_cache(cache):
    os.makedirs(os.path.dirname(NAMEDAY_CACHE_FILE), exist_ok=True)
    tmp_path = f"{NAMEDAY_CACHE_FILE}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp_path, NAMEDAY_CACHE_FILE)
    with contextlib.suppress(OSError):
        os.chmod(NAMEDAY_CACHE_FILE, 0o600)


def nameday_cache_entry(target_date):
    return load_nameday_cache().get(nameday_key(target_date), {})


def cached_nameday(target_date):
    entry = nameday_cache_entry(target_date)
    if isinstance(entry, dict):
        return str(entry.get("name") or "").strip()
    return str(entry or "").strip()


def nameday_cache_checked_at_ts(target_date):
    entry = nameday_cache_entry(target_date)
    if not isinstance(entry, dict):
        return 0
    raw_value = str(entry.get("checked_at") or "").strip()
    if not raw_value:
        return 0
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).timestamp()
    return 0


def displayable_saint_name(raw_name):
    name = " ".join(str(raw_name or "").split())
    if not name:
        return ""

    prefixes = (
        "Saint ", "Sainte ", "Saints ", "Saintes ",
        "Bienheureux ", "Bienheureuse ", "Bienheureux et Bienheureuses ",
    )
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
            break

    for separator in (" ,", ",", " (", " de ", " d’", " d'"):
        if separator in name:
            name = name.split(separator, 1)[0].strip()
            break

    if not name:
        return ""

    parts = name.split()
    if len(parts) == 1:
        return parts[0]

    compound_starters = {"Jean", "Marie", "Anne", "Charles"}
    if parts[0] in compound_starters and parts[1][:1].isupper():
        return f"{parts[0]} {parts[1]}"
    return parts[0]


def clean_nameday_candidate(value):
    name = strip_html(str(value or ""))
    name = re.sub(r"\s+", " ", name).strip(" .,:;!?\t\r\n")
    if not name:
        return ""
    name = displayable_saint_name(name)
    if not name:
        return ""
    blocked = {
        "notre-dame", "notre dame", "assomption", "nativite", "nativité",
        "toussaint", "ascension", "pentecote", "pentecôte", "rameaux",
        "paques", "pâques", "epiphanie", "épiphanie", "fatima", "fátima",
        "notre", "dame", "vierge", "seigneur",
    }
    if normalize_text(name) in blocked:
        return ""
    if not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", name):
        return ""
    return name[:1].upper() + name[1:]


def first_valid_nameday(value):
    for raw_part in re.split(r"[,;/]", str(value or "")):
        candidate = clean_nameday_candidate(raw_part)
        if candidate:
            return candidate
    return ""


def update_cached_nameday(target_date, name, source):
    name = clean_nameday_candidate(name)
    if not name:
        return
    cache = load_nameday_cache()
    cache[nameday_key(target_date)] = {
        "name": name,
        "source": source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    save_nameday_cache(cache)


def fetch_nameday_from_abalin(target_date):
    response = requests.get(
        "https://nameday.abalin.net/api/V2/date",
        params={"day": target_date.day, "month": target_date.month, "country": "fr"},
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else {}
    if isinstance(data, dict):
        return first_valid_nameday(data.get("fr"))
    return ""


def fetch_nameday_from_fetedujour(target_date):
    month_slugs = {
        1: "janvier", 2: "fevrier", 3: "mars", 4: "avril",
        5: "mai", 6: "juin", 7: "juillet", 8: "aout",
        9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre",
    }
    slug = month_slugs.get(target_date.month)
    if not slug:
        return ""
    response = requests.get(f"https://fetedujour.fr/{slug}/", timeout=5)
    response.raise_for_status()
    text = response.text
    pattern = rf"Fête du {target_date.day}\s+[A-Za-zéûîôàèùçÉÛÎÔÀÈÙÇ]+(?:\s*:\s*|\s*</[^>]+>\s*)([^<\n\r]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return first_valid_nameday(match.group(1)) if match else ""


def get_nameday_for_date(target_date, fetchers=None):
    cached = cached_nameday(target_date)
    fetchers = fetchers or (
        ("nameday.abalin.net", fetch_nameday_from_abalin),
        ("fetedujour.fr", fetch_nameday_from_fetedujour),
    )
    for source, fetcher in fetchers:
        try:
            online_name = fetcher(target_date)
        except Exception as exc:
            print(f"[NAMEDAY ERROR] {source}: {exc}")
            continue
        if online_name:
            if online_name != cached:
                update_cached_nameday(target_date, online_name, source)
            return online_name
    return cached


def extract_modern_name(contenu):
    if not contenu:
        return None
    text = re.split(r"<", contenu, maxsplit=1)[0].strip()
    match = re.match(r"^([A-ZÀ-Ÿa-zà-ÿ]+(?:\s+ou\s+[A-ZÀ-Ÿa-zà-ÿ]+)*)\s*\.", text)
    if not match:
        return None
    parts = re.split(r"\s+ou\s+", match.group(1), flags=re.IGNORECASE)
    return parts[-1].strip() if parts else None
