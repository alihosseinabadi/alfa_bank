"""Gold checks for the evaluation protocol, without organizer records."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app.data_preparation.history_io import write_json,file_hash
from app.ml.ranking_contracts import RankingMaterial
from app.ml.prior_ranking import PriorPolicy

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("quality_eval",ROOT/"scripts/evaluate_stage56.py")
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

def test_bootstrap_never_invents_gain_for_unchanged_rankings():
    result=audit.paired_delta([0.0]*5)
    assert result["mean_delta"]==0 and result["bootstrap95"]==[0,0]
    assert audit.paired_delta([1.0]*5)["bootstrap95"]==[1,1]

def test_frozen_collection_cannot_be_overwritten(tmp_path):
    (tmp_path/"collection_manifest.json").write_text("{}")
    with pytest.raises(FileExistsError,match="Frozen"):
        audit.collect(SimpleNamespace(eval_dir=tmp_path))

def fixture_collection(path,labels):
    payloads={"freeze.json":{"prior_policy":PriorPolicy().model_dump(),"code_sha256":audit.current_code_hashes()},
        "blind_pool.json":[{"case":{"case_id":"synthetic"},"cards":[{"material_key":"article:synthetic"}]}],
        "rankings.json":[],"pool_judgments.json":labels,"seed_judgments.json":[]}
    for name,value in payloads.items():write_json(path/name,value)
    write_json(path/"collection_manifest.json",{"files":{name:file_hash(path/name) for name in payloads if name!="pool_judgments.json"},"collection_id":"synthetic"})

def test_unjudged_pool_is_rejected_instead_of_silently_scored_zero(tmp_path):
    fixture_collection(tmp_path,[])
    with pytest.raises(ValueError,match="Incomplete blind pool"):
        audit.score(SimpleNamespace(eval_dir=tmp_path))

def test_modified_frozen_rankings_are_rejected(tmp_path):
    fixture_collection(tmp_path,[])
    (tmp_path/"rankings.json").write_text("[1]")
    with pytest.raises(ValueError,match="Checksum"):
        audit.score(SimpleNamespace(eval_dir=tmp_path))

def test_history_profile_has_actual_corroborating_catalog_material():
    owner=RankingMaterial(material_key="course:synthetic",title="Обучение",item_type="course",
        url="https://example.invalid/course",access_type="Открытый",topics=["Финансы"],
        is_discoverable=True,url_state="unchecked")
    profile,context=audit.evaluation_context({"history_topics":["Финансы"],"task":""},[owner],"catalog")
    assert context.query_source=="inferred_topics"
    assert profile.topic_evidence[0].supporting_material_keys==["course:synthetic"]
    assert profile.catalog_bundle_id=="catalog"
    assert profile.support_material_count==1
