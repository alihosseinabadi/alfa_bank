"""LSA retrieval: TruncatedSVD over stemmed TF-IDF, cosine in latent space.

Why: stemming fixes inflection but not synonymy. A 120-component SVD over the
stemmed term-document matrix pulls ``юнит-экономика`` and ``LTV`` closer without
any trained embedding model, so it stays inside the "no transformer in the
default path" constraint.

Artifacts are explicit and hash-identified: a directory with ``manifest.json``,
``vocabulary.json``, ``idf.npy``, ``components.npz`` and ``documents.npz``. No
pickles are written or read.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.sparse import csr_matrix, load_npz, save_npz
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from .profile_contracts import CONTEXT_VERSION
from .profile_policy import fingerprint
from .retrieval_contracts import LightRetrievalPolicy
from .ru_normalize import analyze
from .tfidf_retriever import eligible_for_context, prepare_corpus, strip_passage
from .synonyms import SynonymDictionary, load_dictionary

CHANNEL = "lsa"
ARTIFACT_FILES = ("vocabulary.json", "idf.npy", "components.npz", "documents.npz")


def _tokens(text: str, canonical: dict[str, str] | None) -> list[str]:
    return analyze(strip_passage(text), canonical)


class LsaRetriever:
    """Latent semantic retrieval with a versioned, hash-checked artifact."""

    def __init__(self, policy: LightRetrievalPolicy | None = None, dictionary: SynonymDictionary | None = None):
        self.policy = policy or LightRetrievalPolicy()
        if self.policy.version != LightRetrievalPolicy().version:
            raise ValueError("Incompatible light retrieval policy")
        self.dictionary = dictionary if dictionary is not None else load_dictionary()
        self.materials: dict = {}
        self.rows: list = []
        self.vectorizer: TfidfVectorizer | None = None
        self.documents: np.ndarray | None = None
        self.components = 0
        self.bundle_id: str | None = None
        self._svd: TruncatedSVD | None = None

    # -- fitting ---------------------------------------------------------
    def fit(self, materials, chunks):
        self.materials, self.rows = prepare_corpus(materials, chunks)
        canonical = self.dictionary.canonical_map
        texts = [" ".join(_tokens(row.text, canonical)) for row in self.rows]
        texts = [text if text.strip() else "_empty_" for text in texts]
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
        matrix = self.vectorizer.fit_transform(texts).tocsr() if texts else None
        if matrix is None or min(matrix.shape) < 3:
            self.documents = None
            self.components = 0
            return self
        limit = min(matrix.shape[0] - 1, matrix.shape[1] - 1, self.policy.lsa_components)
        if limit < 2:
            self.documents = None
            self.components = 0
            return self
        svd = TruncatedSVD(n_components=limit, random_state=self.policy.lsa_random_state, n_iter=7)
        documents = svd.fit_transform(matrix)
        self._svd = svd
        self.documents = self._normalize(documents)
        self.components = limit
        self._set_identity()
        return self

    @staticmethod
    def _normalize(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return np.asarray(matrix / norms, dtype=np.float64)

    def _set_identity(self) -> None:
        payload = {
            "version": self.policy.version,
            "tokenizer_version": self.policy.tokenizer_version,
            "dictionary": self.dictionary.identity,
            "components": self.components,
            "documents": int(self.documents.shape[0]) if self.documents is not None else 0,
            "vocabulary": len(self.vectorizer.vocabulary_) if self.vectorizer else 0,
        }
        self.bundle_id = fingerprint(payload)

    # -- query -----------------------------------------------------------
    def query(self, context, k: int = 50):
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if self.documents is None or not self.rows or not context.query_text.strip():
            return []
        tokens = _tokens(context.query_text, self.dictionary.canonical_map)
        if not tokens:
            return []
        vector = self.vectorizer.transform([" ".join(tokens)])
        if not vector.nnz:
            return []
        projected = self._normalize(np.asarray(self._project(vector)))
        scores = (self.documents @ projected.T).ravel()
        best: dict[str, tuple[float, object]] = {}
        for index, score in enumerate(scores):
            if score < self.policy.lsa_min_similarity:
                continue
            row = self.rows[index]
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

    def _project(self, vector):
        if self._svd is None:
            raise ValueError("LSA artifact is not loaded")
        return self._svd.transform(vector)

    # -- artifacts -------------------------------------------------------
    def save(self, directory: Path | str) -> Path:
        if self.documents is None or self.vectorizer is None:
            raise ValueError("Nothing to save: LSA was not fitted")
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".lsa-building-", dir=output) as tmp:
            stage = Path(tmp)
            (stage / "vocabulary.json").write_text(
                json.dumps(self.vectorizer.vocabulary_, sort_keys=True), encoding="utf-8"
            )
            np.save(stage / "idf.npy", self.vectorizer.idf_, allow_pickle=False)
            save_npz(stage / "components.npz", csr_matrix(self._svd.components_))
            save_npz(stage / "documents.npz", csr_matrix(self.documents))
            files = {name: fingerprint_path(stage / name) for name in ARTIFACT_FILES}
            payload = {
                "version": self.policy.version,
                "tokenizer_version": self.policy.tokenizer_version,
                "dictionary": self.dictionary.identity,
                "components": self.components,
                "documents": int(self.documents.shape[0]),
                "files": files,
            }
            identity = fingerprint(payload)
            (stage / "manifest.json").write_text(
                json.dumps(dict(payload, bundle_id=identity), sort_keys=True, indent=2),
                encoding="utf-8",
            )
            final = output / identity
            if final.exists():
                raise FileExistsError("Immutable LSA artifact already exists")
            os.replace(stage, final)
        return final

    @classmethod
    def load(cls, path: Path | str, *, policy: LightRetrievalPolicy | None = None,
             dictionary: SynonymDictionary | None = None) -> "LsaRetriever":
        directory = Path(path)
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        payload = {key: value for key, value in manifest.items() if key != "bundle_id"}
        if fingerprint(payload) != manifest["bundle_id"]:
            raise ValueError("LSA manifest identity mismatch")
        for name in ARTIFACT_FILES:
            if fingerprint_path(directory / name) != manifest["files"][name]:
                raise ValueError(f"LSA payload changed: {name}")
        instance = cls(policy=policy, dictionary=dictionary)
        instance.vectorizer = TfidfVectorizer(
            tokenizer=str.split,
            token_pattern=None,
            lowercase=False,
            ngram_range=(1, 2),
            min_df=1,
            sublinear_tf=True,
            norm="l2",
            dtype=np.float64,
            vocabulary=json.loads((directory / "vocabulary.json").read_text(encoding="utf-8")),
        )
        instance.vectorizer.idf_ = np.load(directory / "idf.npy", allow_pickle=False)
        instance._svd = TruncatedSVD(
            n_components=manifest["components"], random_state=instance.policy.lsa_random_state
        )
        instance._svd.components_ = load_npz(directory / "components.npz").toarray()
        instance.documents = load_npz(directory / "documents.npz").toarray()
        instance.components = manifest["components"]
        instance.bundle_id = manifest["bundle_id"]
        return instance


def fingerprint_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
