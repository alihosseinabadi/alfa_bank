"""Dense latent-semantic retrieval over public chunks.

The private E5 weights are not part of this repository.  This module provides the
same serving contract with a real, trainable dense channel: TF-IDF over the
Russian analyzer followed by truncated SVD (latent semantic analysis).  Vectors
are persisted as a versioned dataset so the API can load the exact matrix that
was built with the catalogue instead of retraining on every start.

The point is not to claim E5 quality.  It is a genuine dense vector index with
cosine similarity, trained on the public demo corpus, and it can be replaced by
``E5Retriever`` when the private model directory is supplied.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.sparse import load_npz, save_npz
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from .profile_contracts import CONTEXT_VERSION
from .ru_text import analyze_text
from .tfidf_retriever import eligible_for_context, prepare_corpus

EMBEDDING_VERSION = "lsa-tfidf-svd-v2"
ANALYZER_VERSION = "ru-stem-syn-v2"
DATASET_FILES = (
    "rows.jsonl", "vocabulary.json", "idf.npy", "matrix.npz",
    "components.npy", "vectors.npy",
)


def dense_document(material, text: str) -> str:
    """Chunk text plus the catalogue fields that carry its meaning.

    The chunk already starts with the material title, so the title is not
    repeated. Descriptions, topics and tags are the curated context a reader
    sees on the card; without them the dense channel only sees body prose.
    """
    context = [
        *(getattr(material, "descriptions", None) or []),
        *(getattr(material, "topics", None) or []),
        *(getattr(material, "tags", None) or []),
    ]
    context = [part.strip() for part in context if isinstance(part, str) and part.strip()]
    return (" ".join(context) + " " + text).strip() if context else text


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")


class LsaRetriever:
    """Dense channel: TF-IDF -> truncated SVD -> L2-normalised vectors."""

    def __init__(self, n_components: int = 64, min_similarity: float = 0.02,
                 random_state: int = 42, n_iter: int = 10):
        if not isinstance(n_components, int) or isinstance(n_components, bool) or n_components < 2:
            raise ValueError("n_components must be an integer >= 2")
        if not isinstance(n_iter, int) or isinstance(n_iter, bool) or n_iter < 1:
            raise ValueError("n_iter must be a positive integer")
        if not np.isfinite(min_similarity) or not -1 <= min_similarity <= 1:
            raise ValueError("Invalid cosine threshold")
        self.n_components = n_components
        self.min_similarity = float(min_similarity)
        self.random_state = int(random_state)
        self.n_iter = n_iter
        self.materials: dict = {}
        self.rows: list = []
        self.vectorizer: TfidfVectorizer | None = None
        self.svd: TruncatedSVD | None = None
        self.matrix = None
        self.vectors: np.ndarray | None = None

    def fit(self, materials, chunks):
        owners, rows = prepare_corpus(materials, chunks)
        if not rows:
            raise ValueError("Cannot fit a dense index on an empty corpus")
        texts = [dense_document(owners[row.material_key], row.text) for row in rows]
        vectorizer = TfidfVectorizer(
            analyzer=analyze_text, token_pattern=None, lowercase=False,
            sublinear_tf=True, norm="l2", dtype=np.float64,
        )
        matrix = vectorizer.fit_transform(texts)
        if matrix.shape[1] < 2 or matrix.shape[0] < 2:
            raise ValueError("Dense index needs at least two rows and two terms")
        components = min(self.n_components, matrix.shape[0] - 1, matrix.shape[1] - 1)
        svd = TruncatedSVD(
            n_components=components, random_state=self.random_state,
            n_iter=self.n_iter, algorithm="randomized",
        )
        vectors = normalize(svd.fit_transform(matrix))
        if not np.isfinite(vectors).all() or not np.isfinite(svd.components_).all():
            raise ValueError("Dense index produced non-finite values")
        self.materials, self.rows = owners, rows
        self.vectorizer, self.svd = vectorizer, svd
        self.matrix, self.vectors = matrix, vectors.astype(np.float32)
        return self

    def query(self, context, k: int = 50):
        """Return (material key, cosine similarity, best chunk) for the query."""
        if context.schema_version != CONTEXT_VERSION:
            raise ValueError("Incompatible request context")
        if not isinstance(k, int) or isinstance(k, bool) or k < 1:
            raise ValueError("k must be a positive integer")
        if self.vectors is None or self.vectorizer is None or self.svd is None:
            raise ValueError("Dense index has not been fitted")
        if not self.rows or not context.query_text.strip():
            return []
        sparse = self.vectorizer.transform([context.query_text])
        if sparse.nnz == 0:
            return []
        query = normalize(self.svd.transform(sparse))
        if not np.isfinite(query).all() or not np.any(query):
            return []
        scores = self.vectors @ query[0].astype(np.float32)
        best = {}
        for index, row in enumerate(self.rows):
            score = float(scores[index])
            if score < self.min_similarity:
                continue
            if not eligible_for_context(self.materials[row.material_key], context):
                continue
            previous = best.get(row.material_key)
            if previous is None or score > previous[0] or (score == previous[0] and row.chunk_id < previous[1].chunk_id):
                best[row.material_key] = (score, row)
        return [
            (key, score, row)
            for key, (score, row) in sorted(best.items(), key=lambda item: (-item[1][0], item[0]))[:min(k, 50)]
        ]

    # ------------------------------------------------------------------ dataset
    def save(self, directory, metadata: dict | None = None) -> Path:
        if self.vectors is None or self.matrix is None or self.vectorizer is None or self.svd is None:
            raise ValueError("Dense index has not been fitted")
        output = Path(directory)
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".dense-building-", dir=output) as temp:
            stage = Path(temp)
            with (stage / "rows.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
                for row in self.rows:
                    stream.write(json.dumps(row.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
            _write_json(stage / "vocabulary.json", self.vectorizer.vocabulary_)
            np.save(stage / "idf.npy", self.vectorizer.idf_, allow_pickle=False)
            save_npz(stage / "matrix.npz", self.matrix)
            np.save(stage / "components.npy", self.svd.components_, allow_pickle=False)
            np.save(stage / "vectors.npy", self.vectors, allow_pickle=False)
            hashes = {path.name: _file_hash(path) for path in sorted(stage.iterdir())}
            payload = {
                "embedding_version": EMBEDDING_VERSION,
                "analyzer_version": ANALYZER_VERSION,
                "n_components": int(self.svd.components_.shape[0]),
                "n_rows": len(self.rows),
                "n_materials": len({row.material_key for row in self.rows}),
                "n_features": int(self.matrix.shape[1]),
                "min_similarity": self.min_similarity,
                "random_state": self.random_state,
                "n_iter": self.n_iter,
                "files": hashes,
                **(metadata or {}),
            }
            identity = hashlib.sha256(
                json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            _write_json(stage / "manifest.json", dict(payload, bundle_id=identity))
            final = output / identity
            if final.exists():
                existing = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
                if existing != dict(payload, bundle_id=identity):
                    raise ValueError("Dense dataset identity collision")
            else:
                os.replace(stage, final)
            (output / "CURRENT.tmp").write_text(identity + "\n", encoding="utf-8")
            os.replace(output / "CURRENT.tmp", output / "CURRENT")
        return final

    @classmethod
    def load(cls, directory):
        output = Path(directory)
        identity = (output / "CURRENT").read_text(encoding="utf-8").strip()
        path = output / identity
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        payload = {key: value for key, value in manifest.items() if key != "bundle_id"}
        expected = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if expected != manifest.get("bundle_id") or manifest.get("embedding_version") != EMBEDDING_VERSION:
            raise ValueError("Invalid dense dataset manifest")
        if set(manifest.get("files", {})) != set(DATASET_FILES):
            raise ValueError("Incomplete dense dataset")
        for name, digest in manifest["files"].items():
            if _file_hash(path / name) != digest:
                raise ValueError("Dense dataset file checksum mismatch")

        model = cls(
            n_components=int(manifest["n_components"]),
            min_similarity=float(manifest["min_similarity"]),
            random_state=int(manifest["random_state"]),
            n_iter=int(manifest["n_iter"]),
        )
        from .retrieval_contracts import PublicSearchChunk

        rows = []
        with (path / "rows.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    rows.append(PublicSearchChunk.model_validate(json.loads(line)))
        vocabulary = json.loads((path / "vocabulary.json").read_text(encoding="utf-8"))
        idf = np.load(path / "idf.npy", allow_pickle=False)
        matrix = load_npz(path / "matrix.npz").tocsr()
        components = np.load(path / "components.npy", allow_pickle=False)
        vectors = np.load(path / "vectors.npy", allow_pickle=False)
        if matrix.shape != (len(rows), len(vocabulary)) or len(idf) != len(vocabulary):
            raise ValueError("Dense dataset shape mismatch")
        vectorizer = TfidfVectorizer(
            analyzer=analyze_text, token_pattern=None, lowercase=False,
            sublinear_tf=True, norm="l2", dtype=np.float64, vocabulary=vocabulary,
        )
        vectorizer.idf_ = idf
        svd = TruncatedSVD(
            n_components=components.shape[0], random_state=model.random_state,
            n_iter=model.n_iter, algorithm="randomized",
        )
        recomputed = normalize(svd.fit_transform(matrix))
        if recomputed.shape != vectors.shape or not np.allclose(recomputed, vectors, rtol=1e-5, atol=1e-6):
            raise ValueError("Dense vectors do not match their training matrix")
        model.vectorizer, model.svd = vectorizer, svd
        model.matrix, model.vectors = matrix, vectors
        model.rows = rows
        return model

    def attach_materials(self, materials) -> None:
        """Attach the catalogue owner map after loading a vectors-only dataset."""
        self.materials = {material.material_key: material for material in materials}
        if len(self.materials) != len(materials):
            raise ValueError("Duplicate catalog material")
        missing = {row.material_key for row in self.rows} - set(self.materials)
        if missing:
            raise ValueError("Dense rows reference materials missing from the catalogue")
        self.vectors = np.asarray(self.vectors, dtype=np.float32)
        self.min_similarity = float(self.min_similarity)
