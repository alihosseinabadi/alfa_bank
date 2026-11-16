"""Experimental filtered E5/BM25 reciprocal-rank fusion."""
import math
from .retrieval_fusion import reciprocal_rank_fusion
from .tfidf_retriever import tokenize_text


class HybridRetriever:
    def __init__(self, semantic, lexical, *, semantic_threshold, rank_constant=60, min_query_coverage=0.3):
        if not math.isfinite(semantic_threshold) or not -1 <= semantic_threshold <= 1:
            raise ValueError("A valid explicit semantic threshold is required")
        if semantic.materials != lexical.materials or semantic.rows != lexical.rows:
            raise ValueError("Hybrid channels must use the same public corpus")
        if not math.isfinite(min_query_coverage) or not 0 <= min_query_coverage <= 1:
            raise ValueError("Invalid query coverage")
        self.min_query_coverage = min_query_coverage
        self.semantic = semantic
        self.lexical = lexical
        self.semantic_threshold = semantic_threshold
        self.rank_constant = rank_constant

    def query(self, context, k=50):
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if not context.query_text.strip():
            return []
        terms = set(tokenize_text(context.query_text))
        if not terms or sum(term in self.lexical.postings for term in terms) / len(terms) < self.min_query_coverage:
            return []
        semantic = [entry for entry in self.semantic.query(context, 50) if entry[1] >= self.semantic_threshold]
        lexical = self.lexical.query(context, 50)
        return reciprocal_rank_fusion({'semantic': semantic, 'lexical': lexical}, k=k, rank_constant=self.rank_constant)