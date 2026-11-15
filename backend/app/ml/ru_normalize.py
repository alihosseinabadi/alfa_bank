"""Russian-aware analysis for the light retrieval path.

This module is deliberately separate from ``tfidf_retriever.tokenize_text`` so the
existing ``tfidf-search-v1`` index keeps its exact behaviour. Nothing here is
imported by the legacy retrievers.

What it does:

1. Reuses the shared tokenizer (NFKC, casefold, Russian stop words, ``1С``/``НДС``
   style tokens preserved).
2. Stems Cyrillic tokens only, with a cached Snowball stemmer. Latin and digit
   tokens (``LTV``, ``CAC``, ``ИП``/``IP``, ``1С``) are returned untouched.
3. Optionally lemmatizes with ``pymorphy3`` when that package is installed. The
   fallback is Snowball, so the default path has no extra dependency beyond
   ``snowballstemmer``.
4. Optionally canonicalizes curated synonym groups (``удерживать`` and
   ``удержать`` collapse to one token) *before* indexing, so the same material is
   reachable through either word form.

Analysis is pure, deterministic and cached; there is no global state beyond the
``lru_cache`` entries.
"""
from __future__ import annotations

from functools import lru_cache

from .tfidf_retriever import normalize_text, tokenize_text

CYRILLIC_START = "\u0400"
CYRILLIC_END = "\u04ff"

# Tokens this short are never stemmed: ИП, ООО, НДС, 1С, LTV, CAC, РКО.
SHORT_TOKEN_LIMIT = 3

ANALYSIS_VERSION = "ru-stem-v1"


def is_cyrillic(token: str) -> bool:
    """True when at least one character is in the Cyrillic block."""
    return any(CYRILLIC_START <= char <= CYRILLIC_END for char in token)


@lru_cache(maxsize=1)
def _snowball_russian():
    from snowballstemmer import stemmer

    return stemmer("russian")


@lru_cache(maxsize=1)
def _pymorphy():
    """Return a pymorphy3 analyser, or None when the optional package is absent."""
    try:
        import pymorphy3
    except ImportError:
        return None
    return pymorphy3.MorphAnalyzer()


def has_lemmatizer() -> bool:
    return _pymorphy() is not None


@lru_cache(maxsize=50_000)
def stem_token(token: str) -> str:
    """Stem one already-normalized token.

    Latin/digit tokens and very short tokens are returned unchanged so that
    abbreviations stay exact.
    """
    if not is_cyrillic(token) or len(token) <= SHORT_TOKEN_LIMIT:
        return token
    analyser = _pymorphy()
    if analyser is not None:
        return analyser.parse(token)[0].normal_form
    return _snowball_russian().stemWord(token)


def stemmed_tokens(text: str) -> list[str]:
    """Tokenizer + stemmer, no synonym mapping."""
    return [stem_token(token) for token in tokenize_text(text)]


def analyze(text: str, canonical: dict[str, str] | None = None) -> list[str]:
    """Full analysis: tokenize, stem, then apply curated canonical groups."""
    tokens = stemmed_tokens(text)
    if canonical:
        tokens = [canonical.get(token, token) for token in tokens]
    return tokens


def coverage(terms: set[str], vocabulary: set[str]) -> float:
    """Fraction of query terms present in a vocabulary (1.0 when no terms)."""
    if not terms:
        return 0.0
    return len(terms & vocabulary) / len(terms)


def normalize_query(text: str) -> str:
    """Normalized query text for stable hashing and display."""
    return normalize_text(text)
