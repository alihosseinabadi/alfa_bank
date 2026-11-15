"""Synthetic acceptance tests: no organizer text or identities."""
import json
import numpy as np
import pytest
from pydantic import ValidationError
from app.ml.retrieval_contracts import SearchMaterial,PublicSearchChunk,RetrievalPolicy
from app.ml.tfidf_retriever import TfidfRetriever,tokenize_text,normalize_text,eligible_for_context
from app.ml.retrieval_baselines import topic_baseline
from app.ml.user_profile import build_user_profile
from app.ml.request_context import build_request_context
from app.ml.profile_contracts import ExplicitConstraints,ExplicitPreferences
from app.data_preparation.retrieval_bundle import save_index,load_index

def material(key="a",**kwargs):
    return SearchMaterial(material_key=key,title="Налоги бизнеса",item_type="article",
        url="https://example.invalid/"+key,access_type="Открытый",is_discoverable=True,
        url_state="temporary_failure",**kwargs)
def chunk(key="a",identity="c",text="НДС расчет налога",**kwargs):
    return PublicSearchChunk(chunk_id=identity,material_key=key,text=text,source_block_ids=["source:"+identity],**kwargs)
def context(task="НДС",**kwargs):
    profile=build_user_profile("synthetic:test",[],[],ExplicitPreferences())
    return build_request_context(profile,task,ExplicitConstraints(**kwargs))

def test_russian_lexical_normalization():
    assert tokenize_text("Ёлка ёлка 1C 1С НДС НДФЛ 2026")==["елка","елка","1с","1с","ндс","ндфл","2026"]
    assert normalize_text("  ЁЛКА\n")== "елка"

def test_max_pooling_duplicate_before_fit_order_and_ties():
    materials=[material("a"),material("b")]
    rows=[chunk("a","2"),chunk("a","1"),chunk("b","3")]
    first=TfidfRetriever().fit(materials,rows)
    second=TfidfRetriever().fit(list(reversed(materials)),[rows[2],rows[1]])
    assert len(first.rows)==2
    assert first.vectorizer.vocabulary_==second.vectorizer.vocabulary_
    assert np.array_equal(first.vectorizer.idf_,second.vectorizer.idf_)
    assert first.query(context()).model_dump()==second.query(context()).model_dump()
    assert [r.material_key for r in first.query(context()).candidates]==["a","b"]

def test_multiple_different_chunks_are_max_not_sum():
    a,b=material("a"),material("b")
    idx=TfidfRetriever().fit([a,b],[chunk("a","1","НДС налог"),chunk("a","2","НДС расчет"),chunk("b","3","НДС")])
    query=idx.vectorizer.transform(["НДС"])
    best=max((idx.matrix@query.T).toarray().ravel()[:2])
    candidate=next(c for c in idx.query(context()).candidates if c.material_key=="a")
    assert candidate.retrieval_score==pytest.approx(best)
    assert len(idx.query(context()).candidates)==2

@pytest.mark.parametrize("bad",[{"is_discoverable":False},{"url_state":"unavailable"},{"url":"javascript:alert(1)"}])
def test_removed_or_unsafe_cannot_search(bad):
    m=material().model_copy(update=bad)
    idx=TfidfRetriever().fit([m],[chunk(text="СЕКРЕТ НДС")])
    assert not idx.query(context("СЕКРЕТ")).candidates

def test_protected_and_paid_body_rejected():
    with pytest.raises(ValidationError):chunk(access_scope="entitled")
    with pytest.raises(ValueError,match="Paid body"):
        TfidfRetriever().fit([material().model_copy(update={"access_type":"По подписке"})],[chunk(content_kind="body")])
    with pytest.raises(ValueError,match="Orphan"):TfidfRetriever().fit([], [chunk()])

@pytest.mark.parametrize("algorithm",["tfidf","topic"])
def test_constraints_identical_in_both_algorithms(algorithm):
    materials=[material("a",topics=["НДС"]),material("b",topics=["НДС"]).model_copy(update={"access_type":"По подписке","listed_price":0}),
        material("c",topics=["НДС"],duration_minutes=30),material("d",topics=["НДС"]).model_copy(update={"item_type":"course"})]
    idx=TfidfRetriever().fit(materials,[chunk(m.material_key,m.material_key) for m in materials])
    ctx=context(formats=["article"],budget_preference="free_only",available_time_minutes=10)
    result=idx.query(ctx) if algorithm=="tfidf" else topic_baseline(idx,ctx)
    assert [c.material_key for c in result.candidates]==["a"]
    candidate=result.candidates[0]
    assert candidate.duration_fit=="unknown"
    assert "duration_unknown" in candidate.quality_flags
    assert candidate.price_is_unknown

def test_task_history_and_avoidance_invariance():
    idx=TfidfRetriever().fit([material("a"),material("b")],[chunk("a","1","НДС налог"),chunk("b","2","Продажи маркетинг")])
    ctx=context()
    altered=ctx.model_copy(update={"supporting_interests":["Продажи"],"avoidance_topics":["НДС"],"history_weight":0})
    assert idx.query(ctx).model_dump()==idx.query(altered).model_dump()

@pytest.mark.parametrize("query",["","кваркглюонный абракадабра","и для на"])
def test_empty_and_oov_honest(query):
    idx=TfidfRetriever().fit([material()],[chunk()])
    result=idx.query(context(query))
    assert result.status=="needs_clarification" and result.clarification and not result.candidates

def test_weak_threshold_not_filled_with_irrelevant_cards():
    idx=TfidfRetriever(RetrievalPolicy(min_similarity=.99)).fit([material()],[chunk(text="НДС налог доход касса отчет учет выручка прибыль")])
    assert idx.query(context()).status=="needs_clarification"

def test_six_demo_and_fifty_cap():
    materials=[material(str(i)) for i in range(60)]
    idx=TfidfRetriever().fit(materials,[chunk(m.material_key,m.material_key) for m in materials])
    assert len(idx.query(context(),100).candidates)==50
    assert len(idx.query(context(),6).candidates)==6
    for k in (0,-1,True,1.5):
        with pytest.raises(ValueError):idx.query(context(),k)

def test_general_start_is_explicit_and_respects_constraints():
    idx=TfidfRetriever(RetrievalPolicy(starter_keys=["a","a","b"])).fit(
        [material("a"),material("b").model_copy(update={"access_type":"По подписке"})],
        [chunk("a","1"),chunk("b","2")])
    result=idx.query(context("",budget_preference="free_only"))
    assert result.status=="starter" and len(result.candidates)==1
    assert result.candidates[0].retrieval_score==0
    assert result.candidates[0].reason_code=="general_start"
    assert not idx.query(context("глюон")).candidates

def test_evidence_and_next_step_are_public():
    idx=TfidfRetriever().fit([material()],[chunk(text="passage: НДС\n\nТолько публичный текст")])
    result=idx.query(context()).candidates[0]
    assert result.evidence_chunk_id=="c" and result.evidence_source_ids==["source:c"]
    assert result.evidence_text in idx.rows[0].text
    assert "passage:" not in result.evidence_text
    assert result.next_step.url==result.url
    assert "live_url_not_confirmed" in result.quality_flags

def test_save_load_exact_parity_and_hash_failure(tmp_path):
    idx=TfidfRetriever().fit([material()],[chunk()])
    one=save_index(idx,tmp_path,{"catalog_bundle_id":"catalog"})
    two=save_index(idx,tmp_path,{"catalog_bundle_id":"catalog"})
    assert one==two
    loaded,_=load_index(tmp_path,catalog_bundle_id="catalog",profiles_catalog_bundle_id="catalog")
    assert loaded.query(context()).model_dump()==idx.query(context()).model_dump()
    with pytest.raises(ValueError,match="Incompatible"):load_index(tmp_path,catalog_bundle_id="other")
    (one/"vocabulary.json").write_text("{}")
    with pytest.raises(ValueError,match="Checksum"):load_index(tmp_path)

def test_empty_index_persistence(tmp_path):
    idx=TfidfRetriever().fit([],[])
    save_index(idx,tmp_path,{"catalog_bundle_id":"empty"})
    loaded,_=load_index(tmp_path)
    assert loaded.query(context()).status=="no_eligible"

def test_partial_oov_does_not_use_one_generic_word_as_confident_match():
    idx=TfidfRetriever().fit([material()],[chunk(text="Расчет налога")])
    result=idx.query(context("Расчет кваркглюонного токамака спектрометра лунохода"))
    assert result.status=="needs_clarification"
    assert result.reason_codes==["insufficient_query_coverage"]

def test_unknown_context_and_tokenizer_versions_rejected():
    with pytest.raises(ValueError,match="policy"):
        TfidfRetriever(RetrievalPolicy(tokenizer_version="future"))
    idx=TfidfRetriever().fit([material()],[chunk()])
    with pytest.raises(ValueError,match="context"):
        idx.query(context().model_copy(update={"schema_version":"future"}))

def test_late_public_match_appears_in_excerpt():
    text="Введение без специального термина. "*30+"НДС подробный расчет."
    idx=TfidfRetriever().fit([material()],[chunk(text=text)])
    result=idx.query(context()).candidates[0]
    assert "НДС" in result.evidence_text
    assert result.evidence_text in text and len(result.evidence_text)<=360

def test_metrics_hand_calculated_and_missing_labels_fail():
    from app.ml.retrieval_metrics import judged_metrics
    values=judged_metrics(["a","b"],{"a":3,"b":0,"c":2})
    assert values["success5"]==1 and values["pooled_recall50"]==.5
    assert values["ndcg10"]==pytest.approx(7/(7+3/np.log2(3)))
    with pytest.raises(ValueError,match="Unjudged"):judged_metrics(["x"],{"a":3})
    with pytest.raises(ValueError,match="Duplicate"):judged_metrics(["a","a"],{"a":3})

def test_saved_runtime_version_rejected_even_with_self_consistent_manifest(tmp_path):
    from app.ml.profile_policy import fingerprint
    idx=TfidfRetriever().fit([material()],[chunk()])
    path=save_index(idx,tmp_path,{"catalog_bundle_id":"catalog"})
    manifest=json.loads((path/"manifest.json").read_text())
    manifest["sklearn_version"]="future"
    manifest["bundle_id"]=fingerprint({k:v for k,v in manifest.items() if k!="bundle_id"})
    (path/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="runtime"):load_index(path)

def test_adapter_rejects_cross_scope_provenance(tmp_path,monkeypatch):
    from app.data_preparation import retrieval_bundle as adapter
    row=chunk().model_dump();row.pop("content_kind");row["entitlement_key"]=None
    (tmp_path/"manifest.json").write_text("{}")
    (tmp_path/"public_chunks.jsonl").write_text(json.dumps(row)+"\n")
    block={"block_id":"source:c","material_key":"a","content_kind":"metadata","access_scope":"entitled","entitlement_key":"secret"}
    (tmp_path/"content_blocks.jsonl").write_text(json.dumps(block)+"\n")
    monkeypatch.setattr(adapter,"load_catalog",lambda path:([material()],[],[],{}))
    with pytest.raises(ValueError,match="Protected"):adapter.catalog_search_inputs(tmp_path)

def test_continuation_stays_separate_and_never_grants_access():
    from app.ml.profile_contracts import ContinuationCandidate
    idx=TfidfRetriever().fit([material()],[chunk()])
    ctx=context().model_copy(update={"continuation_candidates":[ContinuationCandidate(
        material_key="course:private",course_user_binding_id="synthetic:binding",candidate_lesson_ids=["synthetic:lesson"])]})
    result=idx.query(ctx)
    assert [c.material_key for c in result.candidates]==["a"]
    assert result.continuation_candidates[0].entitlement_granted is False
    assert result.continuation_candidates[0].requires_access_check
