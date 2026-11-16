"""Frozen evaluation rejects an index from another catalog snapshot."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import evaluate_retrieval

def test_evaluation_rejects_different_index(tmp_path, monkeypatch):
    for name in ("cases.json", "seed_judgments.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    freeze = {"bundle_id": "original-index", "policy": {},
              "cases_sha256": evaluate_retrieval.file_hash(tmp_path / "cases.json"),
              "seeds_sha256": evaluate_retrieval.file_hash(tmp_path / "seed_judgments.json")}
    (tmp_path / "config_freeze.json").write_text(json.dumps(freeze), encoding="utf-8")
    index = SimpleNamespace(policy=SimpleNamespace(model_dump=lambda: {}))
    monkeypatch.setattr(evaluate_retrieval, "load_index", lambda _: (index, {"bundle_id": "different-index"}))
    monkeypatch.setattr(evaluate_retrieval, "collect", lambda *_: [])
    monkeypatch.setattr(sys, "argv", ["evaluate_retrieval.py", "--eval-dir", str(tmp_path)])
    with pytest.raises(ValueError, match="Frozen evaluation changed"):
        evaluate_retrieval.main()

def test_collect_refuses_overwriting_frozen_benchmark(tmp_path, monkeypatch):
    for name in ("cases.json", "seed_judgments.json"):
        (tmp_path / name).write_text("[]", encoding="utf-8")
    frozen = tmp_path / "rankings.json"
    frozen.write_text("existing benchmark", encoding="utf-8")
    index = SimpleNamespace(policy=SimpleNamespace(model_dump=lambda: {}))
    monkeypatch.setattr(evaluate_retrieval, "load_index", lambda _: (index, {"bundle_id": "a"}))
    def fail_if_collect(*args):
        raise AssertionError("collection ran before overwrite guard")
    monkeypatch.setattr(evaluate_retrieval, "collect", fail_if_collect)
    monkeypatch.setattr(sys, "argv", ["evaluate_retrieval.py", "--eval-dir", str(tmp_path), "--collect-only"])
    with pytest.raises(FileExistsError, match="Frozen benchmark exists"):
        evaluate_retrieval.main()
    assert frozen.read_text(encoding="utf-8") == "existing benchmark"