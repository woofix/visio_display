# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import hashlib
import ipaddress
import io
import logging
import os
from datetime import datetime
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps

from constants import PRIVATE_DATA_DIR, UPLOAD_FOLDER
from services.announcement_svc import ALLOWED_RASTER_MIMES, _external_image_headers, _safe_image_url, pexels_search
from services.config_svc import load_config, save_config
from services.keyword_recognition_svc import extract_keywords, normalize_text, tokenize
from services.media_svc import get_all_media, get_media_groups, get_media_url, normalize_group_name


LOGGER = logging.getLogger(__name__)
CACHE_SUBDIR = os.path.join("cache", "image_suggestions")
ALLOWED_CACHE_MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_DOWNLOAD_BYTES = int(os.environ.get("IMAGE_SUGGESTION_MAX_BYTES", 8 * 1024 * 1024))
MAX_CACHE_BYTES = int(os.environ.get("IMAGE_SUGGESTION_CACHE_MAX_BYTES", 256 * 1024 * 1024))
FOOD_SEARCH_QUERIES = {
    "steak": "steak food",
    "frites": "french fries food",
    "pizza": "pizza food",
    "salade": "salad food bowl",
    "poisson": "fish dish food",
    "dessert": "dessert cake food",
    "poulet": "chicken dish food",
    "burger": "burger food",
    "pates": "pasta dish food",
    "riz": "rice dish food",
    "sandwich": "sandwich food",
    "tacos": "tacos food",
    "kebab": "kebab food",
    "soupe": "soup food",
    "omelette": "omelette food",
    "crepe": "crepe food",
    "quiche": "quiche food",
    "lasagne": "lasagna food",
    "couscous": "couscous food",
    "sushi": "sushi food",
    "saumon": "salmon dish food",
}
def cache_dir():
    path = os.path.join(PRIVATE_DATA_DIR, CACHE_SUBDIR)
    os.makedirs(path, exist_ok=True)
    return path


def cached_image_path(filename):
    safe_name = os.path.basename(str(filename or ""))
    if not safe_name:
        return None
    path = os.path.join(cache_dir(), safe_name)
    if not os.path.exists(path):
        return None
    return path


def cached_image_url(filename):
    path = cached_image_path(filename)
    if not path:
        return ""
    return f"/admin/menus/suggestion-cache/{os.path.basename(path)}?v={int(os.path.getmtime(path))}"


def _media_keywords(cfg):
    value = cfg.get("media_keywords", {})
    return value if isinstance(value, dict) else {}


def get_media_keywords(filename, cfg=None):
    cfg = cfg or load_config()
    raw = _media_keywords(cfg).get(filename, [])
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list):
        return []
    words = []
    seen = set()
    for item in raw:
        word = normalize_text(item)
        if word and word not in seen:
            words.append(word[:48])
            seen.add(word)
    return words


def associate_media_keyword(filename, keyword):
    filename = os.path.basename(str(filename or ""))
    keyword = normalize_text(keyword)[:48]
    if not filename or not keyword or not os.path.exists(os.path.join(UPLOAD_FOLDER, filename)):
        return []
    cfg = load_config()
    entries = cfg.setdefault("media_keywords", {})
    current = get_media_keywords(filename, cfg)
    if keyword not in current:
        current.append(keyword)
    entries[filename] = current
    save_config(cfg)
    return current


def _candidate_words(filename, cfg):
    stem = normalize_text(os.path.splitext(filename)[0].replace("_", " "))
    words = tokenize(stem)
    words.extend(get_media_keywords(filename, cfg))
    words.extend(normalize_text(group) for group in get_media_groups(filename, cfg))
    return [word for word in words if word]


def _local_suggestions(detected, *, limit_per_keyword=3):
    cfg = load_config()
    suggestions = []
    for item in detected:
        keyword = item["keyword"]
        keyword_tokens = set(tokenize(keyword))
        ranked = []
        for filename in get_all_media(cfg):
            if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            words = _candidate_words(filename, cfg)
            normalized_words = set(words)
            score = 0
            if keyword in normalized_words:
                score = 100
            elif keyword_tokens and keyword_tokens & normalized_words:
                score = 82
            elif any(keyword in word or word in keyword for word in normalized_words):
                score = 68
            if score:
                preview = get_media_url(filename, context="campaign", generate_missing=True) or ""
                original = get_media_url(filename, context="preview", allow_original=True, generate_missing=True) or preview
                ranked.append({
                    "detected_word": keyword,
                    "score": min(100, int((score + item["score"]) / 2)),
                    "source": "local",
                    "filename": filename,
                    "title": filename,
                    "local_path": os.path.join(UPLOAD_FOLDER, filename),
                    "local_url": original,
                    "preview_url": preview or original,
                    "external_url": "",
                })
        ranked.sort(key=lambda entry: (-entry["score"], entry["filename"].casefold()))
        if len(ranked) > 1:
            top_score = ranked[0]["score"]
            top = [entry for entry in ranked if entry["score"] == top_score]
            rest = [entry for entry in ranked if entry["score"] != top_score]
            offset = datetime.now().toordinal() % len(top)
            ranked = top[offset:] + top[:offset] + rest
        suggestions.extend(ranked[:limit_per_keyword])
    return suggestions


def _external_query(keyword):
    normalized = normalize_text(keyword)
    return FOOD_SEARCH_QUERIES.get(normalized, f"{normalized} food")


def _dish_search_terms(text):
    phrase = " ".join(str(text or "").split())[:120]
    words = tokenize(text)
    terms = []
    if phrase:
        terms.append(phrase)
    if words:
        terms.append(f"{' '.join(words[:6])} food dish")
    deduped = []
    seen = set()
    for term in terms:
        key = normalize_text(term)
        if key and key not in seen:
            deduped.append(term)
            seen.add(key)
    return deduped


def _external_detection_items(text, detected):
    items = []
    dish_terms = _dish_search_terms(text)
    if dish_terms:
        label = " ".join(str(text or "").split())[:80]
        items.append({
            "keyword": label or dish_terms[0],
            "score": 104,
            "query": dish_terms[0],
            "search_terms": dish_terms,
            "is_dish": True,
        })
    for item in detected:
        entry = dict(item)
        entry["query"] = _external_query(item["keyword"])
        items.append(entry)
    if not items:
        normalized = normalize_text(text)
        if normalized:
            items.append({
                "keyword": normalized[:80],
                "score": 70,
                "query": f"{normalized} food",
                "search_terms": [f"{normalized} food"],
                "is_dish": True,
            })
    return items


def _safe_external_image_url(url):
    parsed = urlparse(str(url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast)


def _external_suggestions(detected, *, text="", limit_per_keyword=4):
    suggestions = []
    for item in _external_detection_items(text, detected):
        search_terms = item.get("search_terms") or [item.get("query") or _external_query(item["keyword"])]
        provider_results = []
        for query in search_terms:
            try:
                provider_results.extend(pexels_search(query, limit=limit_per_keyword, orientation="", size=""))
            except Exception as exc:
                LOGGER.info("pexels image suggestion skipped for %s: %s", item["keyword"], exc)
            if len(provider_results) >= limit_per_keyword:
                break
        seen_urls = set()
        for result in provider_results:
            url = result.get("url") or ""
            if url in seen_urls:
                continue
            seen_urls.add(url)
            source = result.get("source") or "external"
            suggestions.append({
                "detected_word": item["keyword"],
                "score": max(35, item["score"]),
                "source": source,
                "filename": "",
                "title": result.get("title") or item["keyword"],
                "local_path": "",
                "local_url": "",
                "preview_url": result.get("thumb_data") or result.get("thumb_url") or "",
                "external_url": url,
                "credit": result.get("credit") or "",
            })
    return suggestions


def suggest_images(text, *, include_external=False, limit=12):
    detected = extract_keywords(text)
    providers = [("local", _local_suggestions)]
    if include_external:
        providers.append(("external", _external_suggestions))
    suggestions = []
    for _name, provider in providers:
        if provider is _external_suggestions:
            suggestions.extend(provider(detected, text=text))
        else:
            suggestions.extend(provider(detected))
    suggestions.sort(key=lambda entry: (-entry["score"], entry["source"], entry.get("title", "")))
    return {
        "keywords": detected,
        "suggestions": suggestions[: max(1, min(48, int(limit or 12)))],
        "fallback": not bool(suggestions),
    }


def _cache_filename(url, content_type):
    parsed = urlparse(url)
    name = normalize_group_name(os.path.splitext(os.path.basename(parsed.path))[0]) or "image"
    digest = _url_digest(url)
    ext = ALLOWED_CACHE_MIMES.get(content_type.split(";", 1)[0].strip().lower(), ".jpg")
    return f"{normalize_text(name).replace(' ', '_')[:48] or 'image'}_{digest}{ext}"


def _url_digest(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _cached_by_url(url):
    digest = _url_digest(url)
    for entry in os.scandir(cache_dir()):
        if entry.is_file() and entry.name.endswith((".jpg", ".jpeg", ".png", ".webp")) and digest in entry.name:
            return {
                "filename": entry.name,
                "local_path": entry.path,
                "local_url": cached_image_url(entry.name),
            }
    return None


def _prune_cache():
    root = cache_dir()
    files = []
    total = 0
    for entry in os.scandir(root):
        if not entry.is_file():
            continue
        size = entry.stat().st_size
        total += size
        files.append((entry.stat().st_mtime, size, entry.path))
    if total <= MAX_CACHE_BYTES:
        return
    for _mtime, size, path in sorted(files):
        try:
            os.remove(path)
            total -= size
        except OSError:
            pass
        if total <= MAX_CACHE_BYTES:
            break


def cache_external_image(url):
    if not (_safe_image_url(url) or _safe_external_image_url(url)):
        raise ValueError("URL externe non autorisée.")
    cached = _cached_by_url(url)
    if cached:
        return cached
    response = requests.get(
        url,
        timeout=(2, 8),
        headers=_external_image_headers("image/avif,image/webp,image/apng,image/*,*/*;q=0.8"),
    )
    response.raise_for_status()
    if not (_safe_image_url(response.url) or _safe_external_image_url(response.url)):
        raise ValueError("Redirection externe non autorisée.")
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type not in ALLOWED_CACHE_MIMES or content_type not in ALLOWED_RASTER_MIMES:
        raise ValueError("Format image non autorisé.")
    if len(response.content) > MAX_DOWNLOAD_BYTES:
        raise ValueError("Image trop volumineuse.")
    filename = _cache_filename(response.url, content_type)
    path = os.path.join(cache_dir(), filename)
    if not os.path.exists(path):
        with Image.open(io.BytesIO(response.content)) as image:
            safe_image = ImageOps.exif_transpose(image)
            safe_image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
            if safe_image.mode not in ("RGB", "RGBA"):
                safe_image = safe_image.convert("RGB")
            safe_image.save(path)
        _prune_cache()
    return {
        "filename": filename,
        "local_path": path,
        "local_url": cached_image_url(filename),
    }
