# Licensed under the GNU General Public License v3.0 (GPL-3.0). Copyright (c) 2026 Eric TOMAS (Woofix). See the LICENSE file for details.

import re
import unicodedata

# Weights by field: higher = more important in ranking
_WEIGHTS = {
    'title':       10,
    'keywords':     6,
    'description':  4,
    'content':      2,
}

# Ordered longest-first so the first matching suffix is stripped
_SUFFIXES = (
    'ments', 'tions', 'tion', 'ites', 'ite', 'ations', 'ation',
    'eurs', 'eur', 'aux', 'eux', 'ers', 'er', 'es', 's', 'x',
)

_STOP_WORDS = {
    'a', 'au', 'aux', 'avec', 'ce', 'ces', 'cet', 'cette', 'dans', 'de', 'des',
    'du', 'elle', 'elles', 'en', 'et', 'il', 'ils', 'la', 'le', 'les', 'leur',
    'leurs', 'lui', 'mais', 'ne', 'nos', 'notre', 'nous', 'ou', 'par', 'pas',
    'pour', 'que', 'qui', 'sa', 'se', 'ses', 'son', 'sur', 'un', 'une', 'vos',
    'votre', 'vous',
    'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'in', 'is', 'it',
    'of', 'on', 'or', 'the', 'to', 'with',
}


def normalize(text):
    """Lowercase, remove accents, collapse punctuation to spaces."""
    if not text:
        return ''
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    text = re.sub(r'[^\w\s]', ' ', text)
    return ' '.join(text.split())


def _stems(word):
    """Return frozenset containing the word and its de-suffixed root."""
    variants = {word}
    for suf in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            variants.add(word[:-len(suf)])
            break
    return frozenset(variants)


def _field_match(tokens, qstems):
    """
    Score how well a set of document tokens matches one query word's stems.
    Returns 2.0 (exact token), 1.0 (prefix match), or 0.0 (no match).
    """
    for stem in qstems:
        if stem in tokens:
            return 2.0
        if len(stem) >= 3 and any(t.startswith(stem) for t in tokens):
            return 1.0
    return 0.0


def _query_terms(query):
    norm = normalize(query)
    return [w for w in norm.split() if len(w) >= 2 and w not in _STOP_WORDS]


def parse_query(query):
    """
    Normalize the query and return a list of stem-frozensets, one per word.
    Words shorter than 2 characters and common stop words are ignored.
    """
    return [_stems(w) for w in _query_terms(query)]


def score_item(item, groups, phrase=''):
    """
    Score a result item dict against pre-parsed query stem groups.

    The item dict may contain any of: title, keywords, description, content.
    Other keys are ignored by the scorer but passed through to the caller.
    Returns a float ≥ 0. Higher = more relevant.
    """
    if not groups:
        return 0.0
    total = 0.0
    matched_groups = set()
    for field, weight in _WEIGHTS.items():
        val = item.get(field) or ''
        if not val:
            continue
        tokens = frozenset(normalize(val).split())
        for i, qsg in enumerate(groups):
            m = _field_match(tokens, qsg)
            if m > 0.0:
                total += m * weight
                matched_groups.add(i)
    # Bonus when every query word matched somewhere in the item
    if len(matched_groups) == len(groups):
        total *= 1.25
    if len(groups) > 1 and phrase:
        for field, weight in _WEIGHTS.items():
            if phrase in normalize(item.get(field) or ''):
                total += weight * len(groups)
    return total


def rank_items(items, query, min_score=0.5):
    """
    Filter and sort items by relevance to query.

    Items below min_score are excluded. Items with the same score keep their
    original relative order (stable sort).
    """
    terms = _query_terms(query)
    groups = [_stems(w) for w in terms]
    if not groups:
        return []
    phrase = ' '.join(terms)
    scored = [(score_item(item, groups, phrase), item) for item in items]
    scored = [(s, it) for s, it in scored if s >= min_score]
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored]
