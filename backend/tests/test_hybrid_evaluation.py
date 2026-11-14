"""Exploratory scoring requires a complete unchanged blinded pool."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import evaluate_hybrid_eval as evaluation
from app.data_preparation.history_io import file_hash


def test_frozen_pool_rejects_changes_and_missing_judgments(tmp_path, monkeypatch):
    case={"case_id":"c", "split":"test", "behavior":None}
    entries={"cases.json":[], "judged_subset.json":[], "freeze.json":{}, "rankings.json":[{"case":case,"methods":{}}],
             "blind_pool.json":[{"case":case,"cards":[{"material_key":"a"}]}],
             "pool_judgments.json":[]}
    for name,value in entries.items(): (tmp_path/name).write_text(json.dumps(value), encoding="utf-8")
    collection={"files":{name:file_hash(tmp_path/name) for name in ("cases.json","judged_subset.json","freeze.json","rankings.json","blind_pool.json")}}
    (tmp_path/"collection_manifest.json").write_text(json.dumps(collection), encoding="utf-8")
    monkeypatch.setattr(sys,"argv",["evaluate_hybrid_eval.py","--eval-dir",str(tmp_path)])
    with pytest.raises(ValueError,match="Every blinded card"):
        evaluation.main()
    (tmp_path/"blind_pool.json").write_text("[]",encoding="utf-8")
    with pytest.raises(ValueError,match="checksum mismatch"):
        evaluation.main()
def test_scores_all_methods_only_after_complete_pool(tmp_path, monkeypatch):
    methods=("tfidf","topic","bm25","e5","hybrid")
    cases=[{"case_id":name,"split":name,"behavior":None} for name in ("dev","test")]
    rankings=[{"case":case,"methods":{name:{"keys":["a"],"latency_ms":5.0} for name in methods}} for case in cases]
    pool=[{"case":case,"cards":[{"material_key":"a"}]} for case in cases]
    judgments=[{"case_id":case["case_id"],"material_key":"a","grade":3} for case in cases]
    entries={"cases.json":cases,"judged_subset.json":["dev","test"],"freeze.json":{},"rankings.json":rankings,"blind_pool.json":pool,"pool_judgments.json":judgments}
    for name,value in entries.items(): (tmp_path/name).write_text(json.dumps(value),encoding="utf-8")
    collection={"files":{name:file_hash(tmp_path/name) for name in ("cases.json","judged_subset.json","freeze.json","rankings.json","blind_pool.json")}}
    (tmp_path/"collection_manifest.json").write_text(json.dumps(collection),encoding="utf-8")
    monkeypatch.setattr(sys,"argv",["evaluate_hybrid_eval.py","--eval-dir",str(tmp_path)])
    evaluation.main()
    result=json.loads((tmp_path/"evaluation.json").read_text(encoding="utf-8"))
    assert result["summary"]["test"]["hybrid"]["ndcg10"]==pytest.approx(1.0)
    assert result["latency"]["hybrid"]["p95_ms"]==5.0
    with pytest.raises(FileExistsError): evaluation.main()