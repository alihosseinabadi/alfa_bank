"""Deterministic BM25 retrieval over the same public, eligible chunks as TF-IDF."""
import math
from collections import Counter, defaultdict

from .profile_contracts import CONTEXT_VERSION
from .tfidf_retriever import prepare_corpus, tokenize_text, eligible_for_context


class BM25Retriever:
    def __init__(self, k1=1.2, b=0.75, min_query_coverage=0.3):
        if not math.isfinite(k1) or not math.isfinite(b) or k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Invalid BM25 parameters")
        if not math.isfinite(min_query_coverage) or not 0 <= min_query_coverage <= 1:
            raise ValueError("Invalid query coverage")
        self.k1, self.b, self.min_query_coverage = k1, b, min_query_coverage
        self.materials, self.rows = {}, []
        self.postings = {}
        self.lengths = []
        self.avg_length = 0.0

    def fit(self, materials, chunks):
        self.materials, self.rows = prepare_corpus(materials, chunks)
        self.lengths = []
        postings = defaultdict(list)
        for i, row in enumerate(self.rows):
            words = tokenize_text(row.text)
            self.lengths.append(len(words))
            for word, count in Counter(words).items():
                postings[word].append((i, count))
        self.postings = dict(postings)
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        return self

    def query(self, context, k=50):
        """Return (material key, BM25 score, evidence chunk), or an empty list."""
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if not self.rows or not context.query_text.strip():
            return []
        terms = set(tokenize_text(context.query_text))
        if not terms or sum(term in self.postings for term in terms) / len(terms) < self.min_query_coverage:
            return []
        scores = defaultdict(float)
        matched_terms = Counter()
        count = len(self.rows)
        for term in sorted(terms):
            posting = self.postings.get(term, ())
            if not posting:
                continue
            idf = math.log1p((count - len(posting) + 0.5) / (len(posting) + 0.5))
            for i, frequency in posting:
                norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_length)
                scores[i] += idf * frequency * (self.k1 + 1) / (frequency + norm)
                matched_terms[i] += 1
        best = {}
        for i, score in scores.items():
            row = self.rows[i]
            if matched_terms[i] / len(terms) < self.min_query_coverage:
                continue
            if not eligible_for_context(self.materials[row.material_key], context):
                continue
            previous = best.get(row.material_key)
            if previous is None or score > previous[0] or (score == previous[0] and row.chunk_id < previous[1].chunk_id):
                best[row.material_key] = (score, row)
        return [(key, score, row) for key, (score, row) in sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:min(k, 50)]]