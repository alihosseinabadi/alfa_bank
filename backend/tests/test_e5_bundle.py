import json
from types import SimpleNamespace
import numpy as np
import pytest
from app.data_preparation import e5_bundle
from app.data_preparation.history_io import file_hash
from test_retrieval_stage5 import material, chunk

def test_vector_bundle_checks_identity_and_payload(tmp_path, monkeypatch):
    model = tmp_path / "model"
    model.mkdir()
    for name in e5_bundle.REQUIRED_MODEL_FILES:
        (model / name).write_text(name)
    weights_hash = file_hash(model / "model.safetensors")
    monkeypatch.setattr(e5_bundle, "EXPECTED_WEIGHTS_SHA256", weights_hash)
    encoder = SimpleNamespace(model_dir=model)
    index = SimpleNamespace(rows=[chunk()], materials={"a": material()})
    vectors = np.zeros((1, 768), dtype=np.float32)
    vectors[0, 0] = 1
    path = tmp_path / "vectors.npy"
    np.save(path, vectors, allow_pickle=False)
    identity = {"index_bundle_id": "original", "rows": 1, "dimensions": 768,
                "pooling": "masked_mean_l2_v1", "model": e5_bundle.EXPECTED_MODEL,
                "revision": e5_bundle.EXPECTED_REVISION,
                "model_files_sha256": {name: file_hash(model / name) for name in e5_bundle.REQUIRED_MODEL_FILES}}
    (tmp_path / "manifest.json").write_text(json.dumps({"identity": identity, "vectors_sha256": file_hash(path)}))
    loaded, _ = e5_bundle.load_e5_vectors(index, {"bundle_id": "original"}, encoder, tmp_path)
    assert loaded.vectors.shape == (1, 768)
    with pytest.raises(ValueError, match="bundle mismatch"):
        e5_bundle.load_e5_vectors(index, {"bundle_id": "different"}, encoder, tmp_path)
    (model / "config.json").write_text("changed")
    with pytest.raises(ValueError, match="model checksum"):
        e5_bundle.load_e5_vectors(index, {"bundle_id": "original"}, encoder, tmp_path)