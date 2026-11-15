"""Character n-gram TF-IDF retrieval (word-form tolerant, no stemming needed).

Char n-grams are the safety net for Russian morphology that Snowball does not
collapse (``удерживать``/``удержать``, ``скидок``/``скидками``): the shared
character surface keeps partial signal even when the stems differ.

The interface matches the other channels: ``fit(materials, chunks)`` and
``query(context, k) -> [(material_key, score, chunk), ...]``.
"""
from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .profile_contracts import CONTEXT_VERSION
from .retrieval_contracts import SUPPORTED_LIGHT_VERSIONS, LightRetrievalPolicy
from .tfidf_retriever import eligible_for_context, normalize_text, prepare_corpus, strip_passage

CHANNEL = "char_ngram"


def analyzed_text(text: str) -> str:
    """Normalized text without stop-word removal; char n-grams want the surface."""
    return normalize_text(strip_passage(text))


class CharNgramRetriever:
    """TF-IDF over ``char_wb`` n-grams with material-level max pooling."""

    def __init__(self, policy: LightRetrievalPolicy | None = None):
        policy = policy or LightRetrievalPolicy()
        if policy.version not in SUPPORTED_LIGHT_VERSIONS:
            raise ValueError("Incompatible light retrieval policy")
        self.policy = policy
        self.materials: dict = {}
        self.rows: list = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None

    def fit(self, materials, chunks):
        self.materials, self.rows = prepare_corpus(materials, chunks)
        low, high = self.policy.char_ngram_range
        if not 1 <= low <= high:
            raise ValueError("Invalid character n-gram range")
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(low, high),
            min_df=1,
            sublinear_tf=True,
            norm="l2",
            dtype=np.float64,
        )
        corpus = [analyzed_text(row.text) for row in self.rows]
        if corpus and any(len(text) >= low for text in corpus):
            self.matrix = self.vectorizer.fit_transform(corpus).tocsr()
        else:
            from scipy.sparse import csr_matrix

            self.matrix = csr_matrix((0, 0), dtype=np.float64)
            self.vectorizer = None
        return self

    def query(self, context, k: int = 50):
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if self.vectorizer is None or not self.rows or not context.query_text.strip():
            return []
        text = analyzed_text(context.query_text)
        if len(text) < self.policy.char_ngram_range[0]:
            return []
        vector = self.vectorizer.transform([text])
        if not vector.nnz:
            return []
        scores = (self.matrix @ vector.T).toarray().ravel()
        best: dict[str, tuple[float, object]] = {}
        for index, score in enumerate(scores):
            row = self.rows[index]
            if score < self.policy.char_min_similarity:
                continue
            if not eligible_for_context(self.materials[row.material_key], context):
                continue
            previous = best.get(row.material_key)
            if previous is None or score > previous[0] or (
                score == previous[0] and row.chunk_id < previous[1].chunk_id
            ):
                best[row.material_key] = (float(score), row)
        limit = min(k, self.policy.max_candidates, 50)
        return [
            (key, score, row)
            for key, (score, row) in sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:limit]
        ]
