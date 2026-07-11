# Licensed under the GNU General Public License v3.0 (GPL-3.0).
# Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import re

from unidecode import unidecode


DEFAULT_KEYWORD_DICTIONARY = {
    "steak": ["viande", "boeuf", "bavette", "entrecote", "grillade", "onglet"],
    "frites": ["pommes de terre", "fries", "potatoes"],
    "pizza": ["pizza", "reine", "margherita", "napolitaine", "calzone"],
    "salade": ["salade", "crudites", "cesar", "caesar", "taboule"],
    "poisson": ["fish", "poisson", "cabillaud", "colin", "lieu", "merlu", "thon"],
    "dessert": ["gateau", "tarte", "fruit", "mousse", "creme", "glace", "brownie"],
    "poulet": ["chicken", "volaille", "pilon", "escalope", "nuggets"],
    "burger": ["hamburger", "cheeseburger"],
    "pates": ["pasta", "spaghetti", "tagliatelles", "penne", "macaroni"],
    "riz": ["rice", "risotto"],
    "sandwich": ["panini", "wrap", "bagel"],
    "tacos": ["taco", "burrito", "fajitas"],
    "kebab": ["doner", "shawarma"],
    "soupe": ["potage", "veloute", "bouillon"],
    "omelette": ["oeuf", "oeufs", "eggs"],
    "crepe": ["galette", "pancake"],
    "quiche": ["tarte salee", "lorraine"],
    "lasagne": ["lasagnes", "lasagna"],
    "couscous": ["semoule", "merguez"],
    "sushi": ["maki", "sashimi"],
    "saumon": ["salmon"],
}

STOP_WORDS = {
    "avec", "aux", "des", "de", "du", "et", "la", "le", "les", "un", "une",
    "menu", "plat", "pour", "sur", "a", "au", "en", "ce", "cet", "cette",
}


def normalize_text(value):
    text = unidecode(str(value or "").lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def singularize_token(token):
    token = normalize_text(token)
    if len(token) > 4 and token.endswith("aux"):
        return token[:-3] + "al"
    if len(token) > 3 and token.endswith(("es", "s")):
        return token[:-1]
    return token


def tokenize(value):
    tokens = []
    seen = set()
    for token in normalize_text(value).split():
        token = singularize_token(token)
        if token and token not in STOP_WORDS and token not in seen:
            tokens.append(token)
            seen.add(token)
    return tokens


def keyword_dictionary(custom_dictionary=None):
    dictionary = {}
    sources = [DEFAULT_KEYWORD_DICTIONARY]
    if isinstance(custom_dictionary, dict):
        sources.append(custom_dictionary)
    for source in sources:
        for key, aliases in source.items():
            normalized_key = singularize_token(key)
            if not normalized_key:
                continue
            values = []
            if isinstance(aliases, str):
                aliases = [aliases]
            if isinstance(aliases, list):
                values = [normalize_text(alias) for alias in aliases if normalize_text(alias)]
            canonical = normalize_text(key)
            dictionary[normalized_key] = {
                "canonical": canonical or normalized_key,
                "aliases": values,
            }
    return dictionary


def extract_keywords(value, custom_dictionary=None):
    tokens = tokenize(value)
    token_set = set(tokens)
    normalized_text = f" {normalize_text(value)} "
    detected = []
    dictionary = keyword_dictionary(custom_dictionary)
    for keyword, entry in dictionary.items():
        aliases = entry["aliases"]
        score = 0
        matched_terms = []
        if keyword in token_set:
            score += 100
            matched_terms.append(keyword)
        for alias in aliases:
            alias_tokens = tokenize(alias)
            if alias and f" {alias} " in normalized_text:
                score += 78
                matched_terms.append(alias)
            elif alias_tokens and any(token in token_set for token in alias_tokens):
                score += 45
                matched_terms.append(alias)
        if score:
            detected.append({
                "keyword": entry["canonical"],
                "score": min(score, 100),
                "matched_terms": matched_terms[:4],
            })
    detected.sort(key=lambda item: (-item["score"], item["keyword"]))
    return detected


def important_words(value, custom_dictionary=None):
    detected = [item["keyword"] for item in extract_keywords(value, custom_dictionary)]
    extras = [token for token in tokenize(value) if token not in detected]
    return detected + extras[:8]
