"""Persist and reload the light hybrid retrieval index.

Only the *inputs* are persisted: the filtered public materials, the public
chunks and the policy. Fitting is deterministic (fixed SVD random state, no
sampling), so loading refits the three channels and then asserts that the
recomputed identity equals the stored one. That makes provenance checks
meaningful without pickling any estimator.

Cost: a load is O(corpus) instead of a pickle read. For the 1,444-material
catalog that is a few seconds, which is acceptable for a CLI and keeps the
artifact auditable.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import scipy
import sklearn

from app.ml.light_hybrid import LightHybridRetriever
from app.ml.profile_policy import fingerprint
from app.ml.retrieval_contracts import LIGHT_RETRIEVAL_VERSION, LightRetrievalPolicy
from app.ml.retrieval_contracts import PublicSearchChunk, SearchMaterial
from app.ml.synonyms import load_dictionary

from .history_io import file_hash, read_jsonl, verify_files, write_jsonl

PAYLOAD_FILES = {"materials.jsonl", "rows.jsonl", "policy.json"}
CODE_PATHS = (
    "backend/app/ml/light_hybrid.py",
    "backend/app/ml/ngram_retriever.py",
    "backend/app/ml/lsa_retriever.py",
    "backend/app/ml/ru_normalize.py",
    "backend/app/ml/synonyms.py",
    "backend/app/ml/bm25_ru_stem.py",
    "backend/app/ml/retrieval_fusion.py",
)


def build_light_index(materials, chunks, policy: LightRetrievalPolicy | None = None):
    """Fit a light hybrid index over already-validated public inputs."""
    policy = policy or LightRetrievalPolicy()
    return LightHybridRetriever(policy).fit(materials, chunks)


def save_light_index(index: LightHybridRetriever, output_dir, root, *, catalog_bundle_id,
                     catalog_files=None) -> Path:
    if index.identity is None:
        raise ValueError("Index is not fitted")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".light-building-", dir=output) as tmp:
        stage = Path(tmp)
        write_jsonl(stage / "materials.jsonl", [index.materials[key] for key in sorted(index.materials)])
        write_jsonl(stage / "rows.jsonl", index.rows)
        (stage / "policy.json").write_text(
            json.dumps(index.policy.model_dump(mode="json"), sort_keys=True, indent=2),
            encoding="utf-8",
        )
        files = {name: file_hash(stage / name) for name in PAYLOAD_FILES}
        payload = {
            "retrieval_version": LIGHT_RETRIEVAL_VERSION,
            "tokenizer_version": index.policy.tokenizer_version,
            "policy": index.policy.model_dump(mode="json"),
            "dictionary_version": index.dictionary.version,
            "dictionary_identity": index.dictionary.identity,
            "identity": index.identity,
            "catalog_bundle_id": catalog_bundle_id,
            "catalog_files": catalog_files,
            "sklearn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "scipy_version": scipy.__version__,
            "code_sha256": {
                str(path): file_hash(Path(root) / path) for path in CODE_PATHS
            },
            "files": files,
            "audit": {
                "materials": len(index.materials),
                "chunks": len(index.rows),
                "lsa_components": index.lsa.components,
                "channels": sorted(index.policy.channel_weights),
            },
        }
        identity = fingerprint(payload)
        (stage / "manifest.json").write_text(
            json.dumps(dict(payload, bundle_id=identity), sort_keys=True, indent=2),
            encoding="utf-8",
        )
        final = output / identity
        if final.exists():
            existing = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
            verify_files(final, existing)
            if existing != dict(payload, bundle_id=identity):
                raise ValueError("Immutable light index snapshot collision")
        else:
            os.replace(stage, final)
        (output / "CURRENT.tmp").write_text(identity + "\n", encoding="utf-8")
        os.replace(output / "CURRENT.tmp", output / "CURRENT")
    return final


def load_light_index(index_dir, *, catalog_bundle_id: str | None = None):
    """Load by refitting the deterministic channels and verifying the identity."""
    directory = Path(index_dir)
    if (directory / "CURRENT").exists():
        directory = directory / (directory / "CURRENT").read_text(encoding="utf-8").strip()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    payload = {key: value for key, value in manifest.items() if key != "bundle_id"}
    if fingerprint(payload) != manifest["bundle_id"]:
        raise ValueError("Light index manifest identity mismatch")
    if manifest["retrieval_version"] != LIGHT_RETRIEVAL_VERSION:
        raise ValueError("Incompatible light retrieval version")
    expected = {
        "sklearn_version": sklearn.__version__,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Incompatible retrieval/runtime version")
    if set(manifest["files"]) != PAYLOAD_FILES:
        raise ValueError("Incomplete light index payload")
    if catalog_bundle_id is not None and manifest["catalog_bundle_id"] != catalog_bundle_id:
        raise ValueError("Incompatible retrieval/catalog snapshot")
    verify_files(directory, manifest)

    materials = read_jsonl(directory / "materials.jsonl", SearchMaterial)
    rows = read_jsonl(directory / "rows.jsonl", PublicSearchChunk)
    policy = LightRetrievalPolicy.model_validate(manifest["policy"])
    dictionary = load_dictionary()
    if dictionary.version != manifest["dictionary_version"]:
        raise ValueError("Synonym dictionary version changed")
    if dictionary.identity != manifest["dictionary_identity"]:
        raise ValueError("Synonym dictionary content changed")
    index = build_light_index(materials, rows, policy)
    if index.identity != manifest["identity"]:
        raise ValueError("Light index reconstruction mismatch")
    return index, manifest
