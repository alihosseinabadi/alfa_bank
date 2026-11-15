"""Curated Russian business synonyms: analysis-time canonicalization and boosts.

Two mechanisms, both deterministic and auditable:

``canonical_map``
    Groups with a ``canonical`` token collapse every listed term to that token
    *before* indexing and before querying. ``удерживать`` and ``удержать`` then
    share a posting list instead of being two unrelated terms.

``expansion_map``
    Every group maps to the other terms of the same group. Expansion is used only
    to *boost* candidates that already exist in the fused ranking and only when
    the expansion term is present in the candidate's own evidence chunk. It never
    introduces a material by itself, so a synonym cannot manufacture a hit.

The dictionary is data, not code: it lives in ``data/synonyms_ru.json``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .profile_policy import fingerprint
from .ru_normalize import stemmed_tokens

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "synonyms_ru.json"


@dataclass(frozen=True)
class SynonymGroup:
    group_id: str
    terms: tuple[str, ...]
    canonical: str | None = None


@dataclass(frozen=True)
class SynonymDictionary:
    version: str
    groups: tuple[SynonymGroup, ...]
    canonical_map: dict[str, str]
    expansion_map: dict[str, frozenset[str]]
    identity: str

    def terms_for(self, tokens: set[str]) -> frozenset[str]:
        """Expansion terms contributed by the groups any token belongs to."""
        extra: set[str] = set()
        for token in tokens:
            extra.update(self.expansion_map.get(token, frozenset()))
        return frozenset(extra - tokens)

    def matched_groups(self, tokens: set[str]) -> tuple[str, ...]:
        """Group ids with at least one analyzed token present in ``tokens``."""
        return tuple(
            group.group_id for group in self.groups if _group_tokens(group) & tokens
        )


EMPTY = SynonymDictionary(
    version="synonyms-none",
    groups=(),
    canonical_map={},
    expansion_map={},
    identity=fingerprint({"version": "synonyms-none"}),
)


def _group_tokens(group: SynonymGroup) -> set[str]:
    tokens: set[str] = set()
    for term in group.terms:
        tokens.update(stemmed_tokens(term))
    return tokens


def load_dictionary(path: Path | str | None = None) -> SynonymDictionary:
    """Load and validate the dictionary; a missing file yields the empty dictionary."""
    source = Path(path) if path is not None else DEFAULT_PATH
    if not source.exists():
        return EMPTY
    raw = json.loads(source.read_text(encoding="utf-8"))
    version = raw.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("Synonym dictionary needs a version")

    groups: list[SynonymGroup] = []
    canonical_map: dict[str, str] = {}
    expansion_map: dict[str, set[str]] = {}
    seen_terms: dict[str, str] = {}

    for entry in raw.get("groups", []):
        group_id = entry["id"]
        terms = tuple(term.strip() for term in entry["terms"] if term.strip())
        if not terms:
            raise ValueError(f"Empty synonym group {group_id!r}")
        canonical = entry.get("canonical")
        group = SynonymGroup(group_id=group_id, terms=terms, canonical=canonical)
        tokens = _group_tokens(group)
        if not tokens:
            raise ValueError(f"Synonym group {group_id!r} has no analyzable terms")

        for term in terms:
            normalized = " ".join(stemmed_tokens(term))
            if not normalized:
                raise ValueError(f"Unanalyzable synonym term {term!r}")
            owner = seen_terms.get(normalized)
            if owner is not None and owner != group_id:
                raise ValueError(f"Term {term!r} belongs to both {owner!r} and {group_id!r}")
            seen_terms[normalized] = group_id

        if canonical is not None:
            canonical_tokens = stemmed_tokens(canonical)
            if len(canonical_tokens) != 1:
                raise ValueError(f"Canonical form must be one token: {canonical!r}")
            for token in tokens:
                canonical_map[token] = canonical_tokens[0]
            tokens.add(canonical_tokens[0])

        for token in tokens:
            expansion_map.setdefault(token, set()).update(tokens - {token})

        groups.append(group)

    payload = {
        "version": version,
        "groups": [
            {"id": group.group_id, "terms": list(group.terms), "canonical": group.canonical}
            for group in groups
        ],
    }
    return SynonymDictionary(
        version=version,
        groups=tuple(groups),
        canonical_map=canonical_map,
        expansion_map={key: frozenset(value) for key, value in expansion_map.items()},
        identity=fingerprint(payload),
    )
