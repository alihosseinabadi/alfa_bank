"""Material-level latent semantic channel for ``light-hybrid-search-v2``.

Why a second semantic design: ``light-hybrid-search-v1`` runs LSA over *chunks*
with 120 components. With 294 chunks that is close to full rank, so the projection
barely compresses anything and behaves like a noisy cosine. This channel instead:

* aggregates every public chunk of a material into **one document per material**,
  because relevance is judged per material and chunk-level centroids add noise;
* uses **40 components** (``semantic_components``) so the projection actually
  summarises the catalogue instead of reproducing it;
* weights the query with the same IDF as the documents and adds curated synonym
  expansion terms at a low weight, so ``клиенты`` can reach ``привлечение`` even
  though the words never appear together in a query.

Everything stays inside the allowed toolbox: TF-IDF, ``TruncatedSVD``, numpy,
scipy. No embeddings, no transformer, no training data. The artifact is
recomputed deterministically from the public corpus (see ``light_index.py``).

The channel is additive: ``light-hybrid-search-v1`` and its chunk-level LSA remain
untouched and selectable.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .profile_contracts import CONTEXT_VERSION
from .profile_policy import fingerprint
from .retrieval_contracts import LIGHT_RETRIEVAL_VERSION_V2, LightRetrievalPolicyV2
from .ru_normalize import analyze
from .synonyms import SynonymDictionary, load_dictionary
from .tfidf_retriever import eligible_for_context, prepare_corpus

CHANNEL = "semantic"


class SemanticRetriever:
    """LSA over material-level stemmed TF-IDF, with IDF-weighted query expansion."""

    def __init__(
        self,
        policy: LightRetrievalPolicyV2 | None = None,
        dictionary: SynonymDictionary | None = None,
    ):
        self.policy = policy or LightRetrievalPolicyV2()
        if self.policy.version != LIGHT_RETRIEVAL_VERSION_V2:
            raise ValueError("Incompatible light retrieval policy")
        self.dictionary = dictionary if dictionary is not None else load_dictionary()
        self.materials: dict = {}
        self.rows: list = []
        self.evidence: dict = {}
        self.keys: list[str] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.documents: np.ndarray | None = None
        self.components = 0
        self.bundle_id: str | None = None
        self._svd: TruncatedSVD | None = None

    # -- fitting ---------------------------------------------------------
    def fit(self, materials, chunks) -> "SemanticRetriever":
        self.materials, self.rows = prepare_corpus(materials, chunks)
        by_material: dict[str, list] = {}
        for row in self.rows:
            by_material.setdefault(row.material_key, []).append(row)
        keys = sorted(by_material)
        self.keys = keys
        self.evidence = {
            key: _evidence_row(by_material[key]) for key in keys
        } if keys else {}

        canonical = self.dictionary.canonical_map
        texts = [
            " ".join(analyze(" ".join(row.text for row in by_material[key]), canonical))
            or "_empty_"
            for key in keys
        ]
        self.vectorizer = TfidfVectorizer(
            tokenizer=str.split,
            token_pattern=None,
            lowercase=False,
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            norm="l2",
            dtype=np.float64,
        )
        if not texts:
            self.documents = None
            return self
        matrix = self.vectorizer.fit_transform(texts).tocsr()
        limit = min(
            matrix.shape[0] - 1,
            matrix.shape[1] - 1,
            self.policy.semantic_components,
        )
        if limit < 2:
            self.documents = None
            return self
        svd = TruncatedSVD(
            n_components=limit,
            random_state=self.policy.semantic_random_state,
            n_iter=7,
        )
        self._svd = svd
        self.documents = normalize(svd.fit_transform(matrix))
        self.components = limit
        self.bundle_id = fingerprint({
            "version": self.policy.version,
            "tokenizer_version": self.policy.tokenizer_version,
            "dictionary": self.dictionary.identity,
            "components": self.components,
            "documents": int(self.documents.shape[0]),
            "vocabulary": len(self.vectorizer.vocabulary_),
        })
        return self

    # -- query -----------------------------------------------------------
    def query(self, context, k: int = 50) -> list:
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if self.documents is None or not self.rows or not context.query_text.strip():
            return []
        vector = self._query_vector(context.query_text)
        if vector is None:
            return []
        projected = normalize(self._svd.transform(vector))
        scores = (self.documents @ projected.T).ravel()
        limit = min(k, self.policy.max_candidates, 50)
        out = []
        for index, score in enumerate(scores):
            if score < self.policy.semantic_min_similarity:
                continue
            key = self.keys[index]
            if not eligible_for_context(self.materials[key], context):
                continue
            out.append((key, float(score), self.evidence[key]))
        out.sort(key=lambda item: (-item[1], item[0]))
        return out[:limit]

    def _query_vector(self, text: str):
        """IDF-weighted term vector; originals 1.0, synonym expansions at a lower weight."""
        tokens = analyze(text, self.dictionary.canonical_map)
        if not tokens:
            return None
        weights: dict[str, float] = {}
        for token in tokens:
            weights[token] = weights.get(token, 0.0) + 1.0
        if self.policy.semantic_synonym_weight > 0:
            for term in self.dictionary.terms_for(set(tokens)):
                weights[term] = max(weights.get(term, 0.0), self.policy.semantic_synonym_weight)
        vocabulary = self.vectorizer.vocabulary_
        columns, values = [], []
        for token, weight in weights.items():
            index = vocabulary.get(token)
            if index is None:
                continue
            columns.append(index)
            values.append(weight * float(self.vectorizer.idf_[index]))
        if not columns:
            return None
        return csr_matrix(
            (values, ([0] * len(columns), columns)),
            shape=(1, len(vocabulary)),
        )


def _evidence_row(rows: list):
    """Deterministic evidence chunk: metadata when available, then lowest chunk id."""
    metadata = [row for row in rows if row.content_kind == "metadata"]
    return min(metadata or rows, key=lambda row: row.chunk_id)
