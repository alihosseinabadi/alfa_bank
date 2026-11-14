"""Diagnostics check actual result properties rather than assuming validity."""
import json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"scripts"))
import summarize_hybrid_diagnostics as diagnostics
from app.data_preparation.history_io import file_hash

def test_diagnostics_detect_duplicate_results(tmp_path, monkeypatch):
    methods={name:{"keys":["a","a"] if name=="hybrid" else ["a"],"latency_ms":2.0} for name in ("tfidf","topic","bm25","e5","hybrid")}
    entries={"freeze.json":{"index_bundle_id":"x"},"rankings.json":[{"case":{"behavior":None},"methods":methods}],"cases.json":[],"blind_pool.json":[]}
    for name,value in entries.items():(tmp_path/name).write_text(json.dumps(value),encoding="utf8")
    collection={"files":{name:file_hash(tmp_path/name) for name in entries}}
    (tmp_path/"collection_manifest.json").write_text(json.dumps(collection),encoding="utf8")
    monkeypatch.setattr(diagnostics,"load_index",lambda _: (SimpleNamespace(materials={"a":object()}),{"bundle_id":"x"}))
    monkeypatch.setattr(diagnostics,"context_for_case",lambda _:object())
    monkeypatch.setattr(diagnostics,"eligible_for_context",lambda *_:True)
    monkeypatch.setattr(sys,"argv",["summarize_hybrid_diagnostics.py","--eval-dir",str(tmp_path)])
    diagnostics.main()
    result=json.loads((tmp_path/"diagnostics.json").read_text(encoding="utf8"))
    assert not result["summary"]["hybrid"]["all_constraints_passed"]
    assert result["summary"]["tfidf"]["all_constraints_passed"]