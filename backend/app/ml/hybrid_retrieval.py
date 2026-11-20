"""Hybrid lexical + dense retrieval over the same public demo corpus.

The lexical channel is BM25 with the Russian analyzer.  The dense channel is the
local LSA vector index (or an E5 index when its private weights are supplied).
Scores are min-max scaled per channel and combined 60/40, so lexical precision
still leads while the vector channel can promote a semantically closer material.
When BM25 finds nothing but the dense encoder recognises the wording, the dense
channel may answer alone; an out-of-vocabulary query stays empty.
"""
from __future__ import annotations

import math

from .retrieval_fusion import normalized_score_fusion


class DenseHybridRetriever:
    def __init__(self, dense, lexical, *, dense_weight: float = 0.4,
                 min_query_coverage: float = 0.3, dense_ratio: float = 0.25,
                 dense_rescue_min: float = 0.5):
        if not math.isfinite(dense_weight) or not 0 <= dense_weight <= 1:
            raise ValueError("Invalid dense channel weight")
        if not math.isfinite(min_query_coverage) or not 0 <= min_query_coverage <= 1:
            raise ValueError("Invalid query coverage")
        if not math.isfinite(dense_ratio) or not 0 <= dense_ratio <= 1:
            raise ValueError("Invalid dense ratio")
        if not math.isfinite(dense_rescue_min) or not 0 <= dense_rescue_min <= 1:
            raise ValueError("Invalid dense rescue threshold")
        if set(dense.materials) != set(lexical.materials):
            raise ValueError("Hybrid channels must use the same public corpus")
        dense_rows = [(row.material_key, row.chunk_id, row.text) for row in dense.rows]
        lexical_rows = [(row.material_key, row.chunk_id, row.text) for row in lexical.rows]
        if dense_rows != lexical_rows:
            raise ValueError("Hybrid channels must use the same public rows")
        self.dense, self.lexical = dense, lexical
        self.dense_weight = float(dense_weight)
        self.min_query_coverage = float(min_query_coverage)
        self.dense_ratio = float(dense_ratio)
        self.dense_rescue_min = float(dense_rescue_min)

    def _dense_candidates(self, context, k: int):
        dense = self.dense.query(context, k)
        if not dense:
            return []
        # Drop the long tail of weak cosine matches; keep at least the best hit.
        floor = max(self.dense.min_similarity, self.dense_ratio * dense[0][1])
        return [entry for entry in dense if entry[1] >= floor]

    def query(self, context, k: int = 50):
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if not context.query_text.strip():
            return []
        # Fuse over the full candidate pool, then cut to k. Requesting only k
        # from each channel makes the fused order depend on the page size.
        pool = max(k, 50)
        lexical = self.lexical.query(context, pool)
        dense = self._dense_candidates(context, pool)
        if not lexical:
            # A genuine paraphrase can share no lexical term with the catalogue.
            # The dense encoder already returns nothing for out-of-vocabulary
            # nonsense, so a strong cosine is the only way this branch fires.
            if dense and dense[0][1] >= self.dense_rescue_min:
                return normalized_score_fusion(
                    {"dense": dense}, k=k, weights={"dense": 1.0})
            return []
        if not dense:
            return normalized_score_fusion(
                {"bm25": lexical}, k=k, weights={"bm25": 1.0})
        return normalized_score_fusion(
            {"bm25": lexical, "dense": dense}, k=k,
            weights={"bm25": 1.0 - self.dense_weight, "dense": self.dense_weight},
        )
