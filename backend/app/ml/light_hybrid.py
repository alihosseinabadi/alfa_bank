"""Light hybrid retrieval: stemmed BM25 + char n-grams + LSA, with an OOD guard.

This is an additive, versioned path (``light-hybrid-search-v1``). The legacy
``tfidf-search-v1`` retriever, its index and its policy are untouched.

Design decisions, all explicit:

* All channels use the same ``prepare_corpus`` output, so the protected/paid
  material checks are inherited unchanged.
* Fusion is reciprocal-rank fusion, so channel scores never have to be on a
  common scale.
* Out-of-domain handling: query-term coverage is measured against the *stemmed*
  vocabulary. Zero coverage means the request has nothing to do with the catalog
  and returns an empty result with ``status="no_eligible"`` and
  ``reason_codes=["query_out_of_domain"]``. Partial coverage below the threshold
  returns ``needs_clarification``. ``no_eligible`` here means "no acceptable
  material", which is the wording the stage-5 check cases expect.
* Synonyms only boost candidates that already exist and only when the expansion
  term is present in the candidate's own evidence chunk. They cannot create a hit.
"""
from __future__ import annotations

from .bm25_ru_stem import RussianStemBM25Retriever
from .lsa_retriever import LsaRetriever
from .ngram_retriever import CharNgramRetriever
from .profile_contracts import CONTEXT_VERSION
from .profile_policy import fingerprint
from .retrieval_contracts import (
    LIGHT_RETRIEVAL_VERSION,
    LightRetrievalPolicy,
    SearchCandidate,
    SearchResult,
)
from .retrieval_fusion import reciprocal_rank_fusion
from .ru_normalize import analyze
from .synonyms import SynonymDictionary, load_dictionary
from .tfidf_retriever import eligible_for_context, make_candidate, prepare_corpus, tokenize_text

NO_CLARIFICATION = "Уточните, пожалуйста, задачу: чем именно помочь?"
NO_DOMAIN_CLARIFICATION = (
    "По этому запросу в каталоге Альфа-Курса нет подходящих материалов. "
    "Опишите задачу в терминах бизнеса — например, продажи, финансы, найм или маркетинг."
)


class LightHybridRetriever:
    """Stemmed, fused retrieval with explicit refusal semantics."""

    def __init__(self, policy: LightRetrievalPolicy | None = None,
                 dictionary: SynonymDictionary | None = None):
        self.policy = policy or LightRetrievalPolicy()
        if self.policy.version != LIGHT_RETRIEVAL_VERSION:
            raise ValueError("Incompatible light retrieval policy version")
        self.dictionary = dictionary if dictionary is not None else load_dictionary()
        self.materials: dict = {}
        self.rows: list = []
        canonical = self.dictionary.canonical_map
        self.bm25 = RussianStemBM25Retriever(
            min_query_coverage=self.policy.min_query_coverage,
            analyzer=lambda text: analyze(text, canonical),
        )
        self.chars = CharNgramRetriever(self.policy)
        self.lsa = LsaRetriever(self.policy, self.dictionary)
        self.identity: str | None = None

    # -- fitting ---------------------------------------------------------
    def fit(self, materials, chunks):
        self.bm25.fit(materials, chunks)
        self.chars.fit(materials, chunks)
        self.lsa.fit(materials, chunks)
        signatures = {
            self._corpus_signature(channel.materials, channel.rows)
            for channel in (self.bm25, self.chars, self.lsa)
        }
        if len(signatures) != 1:
            raise ValueError("Hybrid channels must share one filtered public corpus")
        self.materials = self.bm25.materials
        self.rows = self.bm25.rows
        self.identity = fingerprint({
            "version": self.policy.version,
            "policy": self.policy.model_dump(),
            "dictionary": self.dictionary.identity,
            "corpus": signatures.pop(),
            "lsa": self.lsa.bundle_id,
        })
        return self

    @staticmethod
    def _corpus_signature(materials, rows) -> str:
        return fingerprint({
            "materials": [[m.material_key, m.title, m.item_type, m.access_type, m.url_state]
                          for m in sorted(materials.values(), key=lambda m: m.material_key)],
            "chunks": [[r.chunk_id, r.material_key, r.text] for r in rows],
        })

    # -- query -----------------------------------------------------------
    def query(self, context, k: int = 50) -> SearchResult:
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        k = min(k, self.policy.max_candidates, 50)
        if self.identity is None:
            raise ValueError("Index has not been fitted")

        eligible = {
            key for key, material in self.materials.items() if eligible_for_context(material, context)
        }
        if not eligible:
            return self._refusal(context, "empty_eligible_pool", NO_CLARIFICATION, 0)

        terms = analyze(context.query_text, self.dictionary.canonical_map)
        if not terms:
            return self._starter_or_refusal(context, k, eligible)

        token_set = set(terms)
        matched = token_set & set(self.bm25.postings)
        if not matched:
            return self._refusal(context, "query_out_of_domain", NO_DOMAIN_CLARIFICATION, len(eligible))
        if len(matched) / len(token_set) < self.policy.min_query_coverage:
            return self._refusal(
                context, "insufficient_query_coverage", NO_CLARIFICATION, len(eligible),
                has_vocabulary=True,
            )

        channels = {
            "bm25_stem": self.bm25.query(context, 50),
            "char_ngram": self.chars.query(context, 50),
            "lsa": self.lsa.query(context, 50),
        }
        declared = self.policy.channel_weights
        channels = {
            name: rows for name, rows in channels.items()
            if rows and declared.get(name, 0.0) > 0
        }
        if not channels:
            return self._refusal(context, "no_channel_match", NO_CLARIFICATION, len(eligible),
                                 has_vocabulary=True)
        weights = {name: declared[name] for name in channels}

        fused = reciprocal_rank_fusion(
            channels, k=50, rank_constant=self.policy.rank_constant, weights=weights
        )
        fused, synonym_hits = self._apply_synonyms(fused, token_set)
        ceiling = sum(weights[name] for name in channels) / (self.policy.rank_constant + 1)
        ordered = fused[:k]
        candidates = [
            self._candidate(
                context, key,
                min(1.0, total / ceiling) if ceiling else 0.0,
                evidence, synonym_hits.get(key, ()),
            )
            for key, total, evidence in ordered
        ]
        reason_codes = ["rank_fusion", "stemmed_query", "score_is_not_probability"]
        reason_codes += [f"channel:{name}" for name in sorted(channels)]
        return SearchResult(
            version=LIGHT_RETRIEVAL_VERSION,
            context_id=context.context_id,
            algorithm="light_hybrid",
            status="matched",
            candidates=candidates,
            clarification=None,
            reason_codes=reason_codes,
            eligible_materials=len(eligible),
            query_has_vocabulary=True,
            continuation_candidates=list(context.continuation_candidates),
        )

    # -- helpers ---------------------------------------------------------
    def _apply_synonyms(self, fused, token_set: set[str]):
        """Boost fused candidates whose own evidence contains an expansion term."""
        expansion = self.dictionary.terms_for(token_set)
        if not expansion or self.policy.synonym_weight <= 0:
            return fused, {}
        canonical = self.dictionary.canonical_map
        boosted, hits = [], {}
        for key, total, evidence in fused:
            chunk = min(evidence.values(), key=lambda item: (item["rank"], item["chunk"].chunk_id))["chunk"]
            present = set(analyze(chunk.text, canonical)) & expansion
            if not present:
                boosted.append((key, total, evidence))
                continue
            factor = 1.0 + self.policy.synonym_weight * len(present) / len(expansion)
            boosted.append((key, total * factor, evidence))
            hits[key] = tuple(sorted(present))
        boosted.sort(key=lambda item: (-item[1], item[0]))
        return boosted, hits

    def _candidate(self, context, key, score, evidence, synonym_terms) -> SearchCandidate:
        material = self.materials[key]
        names = sorted(evidence)
        chunk = min(
            evidence.values(), key=lambda item: (item["rank"], item["chunk"].chunk_id)
        )["chunk"]
        candidate = make_candidate(
            material, chunk, score, context, "light_hybrid", tokenize_text(context.query_text)
        )
        channel_list = ", ".join(f"{name}#{evidence[name]['rank']}" for name in names)
        reason = (
            f"Совпадение по смыслу запроса: каналы {channel_list}. "
            "Стеммированный поиск покрывает словоформы, char-ngram — опечатки и "
            "разные основы, LSA — близкие формулировки."
        )
        if synonym_terms:
            reason += f" Учтены синонимы: {', '.join(synonym_terms)}."
        return candidate.model_copy(update={
            "reason_code": "hybrid_fused_match",
            "reason": reason,
            "retrieval_version": LIGHT_RETRIEVAL_VERSION,
        })

    def _refusal(self, context, reason: str, clarification: str, eligible: int,
                 has_vocabulary: bool = False) -> SearchResult:
        return SearchResult(
            version=LIGHT_RETRIEVAL_VERSION,
            context_id=context.context_id,
            algorithm="light_hybrid",
            status="no_eligible",
            candidates=[],
            clarification=clarification,
            reason_codes=[reason],
            eligible_materials=eligible,
            query_has_vocabulary=has_vocabulary,
            continuation_candidates=list(context.continuation_candidates),
        )

    def _starter_or_refusal(self, context, k: int, eligible: set[str]) -> SearchResult:
        starters = []
        for key in dict.fromkeys(self.policy.starter_keys):
            if key not in eligible:
                continue
            material = self.materials[key]
            row = next((row for row in self.rows if row.material_key == key), None)
            if row is None:
                continue
            starters.append(make_candidate(
                material, row, 0.0, context, "light_hybrid", [], starter=True
            ))
            if len(starters) >= k:
                break
        if starters:
            return SearchResult(
                version=LIGHT_RETRIEVAL_VERSION,
                context_id=context.context_id,
                algorithm="light_hybrid",
                status="starter",
                candidates=starters,
                clarification=None,
                reason_codes=["general_start"],
                eligible_materials=len(eligible),
                query_has_vocabulary=False,
                continuation_candidates=list(context.continuation_candidates),
            )
        return SearchResult(
            version=LIGHT_RETRIEVAL_VERSION,
            context_id=context.context_id,
            algorithm="light_hybrid",
            status="needs_clarification",
            candidates=[],
            clarification=NO_CLARIFICATION,
            reason_codes=["empty_query"],
            eligible_materials=len(eligible),
            query_has_vocabulary=False,
            continuation_candidates=list(context.continuation_candidates),
        )
