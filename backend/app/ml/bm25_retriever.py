"""Deterministic BM25 retrieval over the same public, eligible chunks as TF-IDF."""
import math
from collections import Counter, defaultdict

from .profile_contracts import CONTEXT_VERSION
from .ru_text import ANALYZER_VERSION, analyze_text
from .tfidf_retriever import prepare_corpus, eligible_for_context


class BM25Retriever:
    analyzer_version = ANALYZER_VERSION

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
            words = analyze_text(row.text)
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
        content_terms = set(analyze_text(context.query_text, with_concepts=False))
        concepts = set(analyze_text(context.query_text)) - content_terms
        if not content_terms and not concepts:
            return []
        known_content = [term for term in content_terms if term in self.postings]
        known_concepts = [term for term in concepts if term in self.postings]
        if not known_content and not known_concepts:
            return []
        # A question made only of unknown words still gets a clarification.
        if not known_content and len(known_concepts) / max(1, len(concepts)) < self.min_query_coverage:
            return []
        # Up to four query content terms define the per-document requirement, so
        # long conversational queries are not punished for their tail.  A
        # concept-only match is allowed when the user's wording and the catalogue
        # use different synonyms (e.g. "сотрудник" vs "нанять").
        denominator = min(len(content_terms) or 1, 4)
        scores = defaultdict(float)
        raw_matches = Counter()
        concept_matches = Counter()
        count = len(self.rows)
        for term in sorted(content_terms | concepts):
            posting = self.postings.get(term, ())
            if not posting:
                continue
            idf = math.log1p((count - len(posting) + 0.5) / (len(posting) + 0.5))
            for i, frequency in posting:
                norm = self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avg_length)
                scores[i] += idf * frequency * (self.k1 + 1) / (frequency + norm)
                if term in content_terms:
                    raw_matches[i] += 1
                else:
                    concept_matches[i] += 1
        best = {}
        for i, score in scores.items():
            row = self.rows[i]
            raw_coverage = raw_matches[i] / denominator
            if raw_coverage < self.min_query_coverage and not (raw_matches[i] == 0 and concept_matches[i] > 0):
                continue
            if not eligible_for_context(self.materials[row.material_key], context):
                continue
            previous = best.get(row.material_key)
            if previous is None or score > previous[0] or (score == previous[0] and row.chunk_id < previous[1].chunk_id):
                best[row.material_key] = (score, row)
        return [(key, score, row) for key, (score, row) in sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:min(k, 50)]]