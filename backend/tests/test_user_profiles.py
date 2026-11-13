"""MVP interest policy tests with artificial sources, caps and temporal cases."""
import copy
import ast
import json
import math
from pathlib import Path
import pytest
from test_history_stage3 import history_case,history_artifacts
from app.data_preparation.user_history import normalize_history
from app.data_preparation.profile_bundle import build_profiles,verify_profiles,validate_policy_scales
from app.data_preparation.history_io import read_jsonl,resolve_bundle,write_json,file_hash
from app.ml.user_profile import build_user_profile
from app.ml.profile_policy import ProfilePolicy,RatingRule
from app.ml.profile_contracts import ExplicitPreferences,UserProfile

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def policy():
    return ProfilePolicy(rating_rules={"scale":RatingRule(reviewed_group_question="Оцените",reviewed_value_questions={i:"" for i in range(1,6)})})

@pytest.fixture
def profile_case(history_case):
    tables,source,materials,aliases,links=history_case
    data=normalize_history(*history_case)
    return data,materials,tables

def build(case,policy,items=None,**kwargs):
    data,materials,_=case
    return build_user_profile("organizer:u1",items if items is not None else data["profile_inputs"],materials,policy=policy,**kwargs)

def test_one_course_has_bounded_traceable_profile(profile_case,policy):
    profile=build(profile_case,policy)
    assert profile.topic_weights=={"Финансы":1.0}
    assert profile.support_material_count==1 and not profile.cold_start
    assert profile.topic_evidence[0].support_count==1
    assert profile.topic_evidence[0].confidence==pytest.approx(1/3)
    assert profile.explicit_preferences.formats==[]
    assert profile.observed_format_counts=={"course":1}
    assert not profile.confidence_is_calibrated

def test_unknown_user_is_valid_cold_start(profile_case,policy):
    data,materials,_=profile_case
    p=build_user_profile("organizer:unknown",data["profile_inputs"],materials,policy=policy)
    assert p.cold_start and p.cold_start_reason=="no_usable_history"
    assert not p.topic_weights and not p.observed_format_counts
    assert p.explicit_preferences.industry is None and p.explicit_preferences.experience is None

def test_many_lessons_are_capped_per_material(profile_case,policy):
    data,materials,_=profile_case
    lesson=next(o for o in data["profile_inputs"] if o.observation_kind=="lesson_progress")
    other=next(m for m in materials if m.item_type=="article").model_copy(update={"topics":["Маркетинг"]})
    materials=[m for m in materials if m.material_key!=other.material_key]+[other]
    other_lesson=lesson.model_copy(update={"observation_id":"other","material_key":other.material_key})
    one=build_user_profile("organizer:u1",[lesson,other_lesson],materials,policy=policy)
    many=build_user_profile("organizer:u1",[lesson.model_copy(update={"observation_id":str(i)}) for i in range(1000)]+[other_lesson],materials,policy=policy)
    assert one.topic_weights==many.topic_weights=={"Маркетинг":0.5,"Финансы":0.5}
    assert one.support_material_count==many.support_material_count==2
    assert [e.confidence for e in one.topic_evidence]==[e.confidence for e in many.topic_evidence]

def test_duplicate_identity_is_noop_in_current_and_historical_modes(profile_case,policy):
    data,_,_=profile_case
    for cutoff in (None,"2025-02","2025-03"):
        one=build(profile_case,policy,cutoff_month=cutoff)
        duplicate=build(profile_case,policy,items=data["profile_inputs"]*2,cutoff_month=cutoff)
        assert one.model_dump()==duplicate.model_dump()

def test_conflicting_duplicate_identity_fails(profile_case,policy):
    data,_,_=profile_case
    item=next(o for o in data["profile_inputs"] if o.user_key=="organizer:u1")
    conflicting=item.model_copy(update={"material_key":"article:article1"})
    with pytest.raises(ValueError,match="Conflicting observation"):
        build(profile_case,policy,items=[item,conflicting])

@pytest.mark.parametrize("score",[1,2,3])
def test_negative_rating_never_becomes_positive_topic_or_title(profile_case,policy,score):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    items=[o for o in data["profile_inputs"] if o.source_record_id!="r1"]+[
        grade.model_copy(update={"rating_value":score})]
    p=build(profile_case,policy,items)
    assert not p.topic_weights and not p.title_fallbacks
    assert p.avoidance_weights=={"Финансы":1.0}
    assert p.material_evidence[0].negative_strength==1
    assert p.material_evidence[0].net_strength==0

def test_mixed_explicit_feedback_is_preserved_not_arbitrarily_last_wins(profile_case,policy):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    p=build(profile_case,policy,items=[grade,grade.model_copy(update={"observation_id":"negative","rating_value":1})])
    assert p.material_evidence[0].explicit_positive==1
    assert p.material_evidence[0].explicit_negative==1
    assert not p.topic_weights and p.topic_evidence[0].confidence==0

@pytest.mark.parametrize("field,value",[("rating_group_id","unreviewed"),("rating_scale_status","unknown"),("rating_scale_values",[0,1])])
def test_unreviewed_or_unknown_scale_is_not_a_signal(profile_case,policy,field,value):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    p=build(profile_case,policy,items=[grade.model_copy(update={field:value})])
    assert p.cold_start and p.skipped_observations["unreviewed_or_unknown_rating_scale"]==1

def test_unknown_material_is_not_guessed(profile_case,policy):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    ambiguous=build(profile_case,policy,items=[grade.model_copy(update={"material_key":None})])
    assert ambiguous.cold_start and ambiguous.skipped_observations["ambiguous_material"]==1
    with pytest.raises(ValueError,match="missing from pinned"):
        build(profile_case,policy,items=[grade.model_copy(update={"material_key":"course:not-in-catalog"})])

def test_anonymous_rejected_and_foreign_identity_do_not_enter_profile(profile_case,policy):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    for changes in ({"resolution_status":"rejected"},{"source_user_id":None},{"source_user_id":"somebody-else"}):
        p=build(profile_case,policy,items=[grade.model_copy(update=changes)])
        assert not p.topic_weights and p.support_material_count==0

def test_multitopic_material_does_not_gain_extra_total_strength(profile_case,policy):
    data,materials,_=profile_case
    course=next(m for m in materials if m.item_type=="course")
    materials=[m.model_copy(update={"topics":["Финансы","Маркетинг","Маркетинг"]}) if m==course else m for m in materials]
    p=build_user_profile("organizer:u1",data["profile_inputs"],materials,policy=policy)
    assert p.topic_weights=={"Маркетинг":0.5,"Финансы":0.5}
    assert sum(t.positive_strength for t in p.topic_evidence)==1

def test_missing_topics_can_use_supported_positive_title(profile_case,policy):
    data,materials,_=profile_case
    course=next(m for m in materials if m.item_type=="course")
    materials=[m.model_copy(update={"topics":[]}) if m==course else m for m in materials]
    p=build_user_profile("organizer:u1",data["profile_inputs"],materials,policy=policy)
    assert not p.topic_weights and p.title_fallbacks[0].title==course.title
    assert p.title_fallbacks[0].source=="observed_material_title"

def test_explicit_reset_removes_inferred_interests_only(profile_case,policy):
    prefs=ExplicitPreferences(reset_inferred=True,selected_topics=["Продажи"],formats=["document"])
    p=build(profile_case,policy,explicit_preferences=prefs)
    assert p.cold_start and not p.topic_weights and not p.material_evidence
    assert p.explicit_preferences.selected_topics==["Продажи"]

def test_temporal_mode_drops_tied_month_mutable_enrollment_and_learning_reference(profile_case,policy):
    p=build(profile_case,policy,cutoff_month="2025-02")
    assert p.cold_start and p.mode=="historical"
    assert p.learning_state_reference is None
    p=build(profile_case,policy,cutoff_month="2025-03")
    assert p.topic_weights=={"Финансы":1}
    assert "enrollment_state" not in p.material_evidence[0].source_kinds

def test_late_rating_is_not_visible_before_its_available_month(profile_case,policy):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1").model_copy(update={"available_from_month":"2025-04","event_time":"2025-04"})
    p=build(profile_case,policy,items=[grade],cutoff_month="2025-04")
    assert p.cold_start

def test_inputs_are_not_mutated_and_order_is_deterministic(profile_case,policy):
    data,materials,_=profile_case
    before=copy.deepcopy((data,materials))
    p=build(profile_case,policy)
    reverse=build(profile_case,policy,items=list(reversed(data["profile_inputs"])))
    assert p.model_dump()==reverse.model_dump()
    assert data==before[0] and materials==before[1]

def test_weights_and_invalid_input_validation(profile_case,policy):
    p=build(profile_case,policy)
    assert all(math.isfinite(v) and 0<=v<=1 for v in p.topic_weights.values())
    with pytest.raises(ValueError):ProfilePolicy(enrollment_strength=float("nan"))
    with pytest.raises(ValueError):RatingRule(positive_values=[4],negative_values=[4])
    with pytest.raises(ValueError):build(profile_case,policy,cutoff_month="2025-99")
    with pytest.raises(ValueError):ExplicitPreferences(available_time_minutes=0)

def test_ml_modules_have_no_forbidden_imports():
    for path in (ROOT/"backend/app/ml").glob("*.py"):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ""] if isinstance(node,ast.ImportFrom) else []
            assert not any(any(bad in module for bad in ("fastapi","sqlalchemy","experiments","app.services","app.data_preparation")) for module in modules)

@pytest.fixture
def profile_artifacts(history_artifacts,tmp_path,policy):
    from app.data_preparation.history_bundle import build_history
    source,catalog,history=history_artifacts
    build_history(source,catalog,history,ROOT)
    return source,catalog,history,tmp_path/"profiles",policy

def test_profiles_bundle_repeatability_and_independent_reconstruction(profile_artifacts):
    source,catalog,history,output,policy=profile_artifacts
    first,audit=build_profiles(history,catalog,source,output,ROOT,policy=policy)
    second,_=build_profiles(history,catalog,source,output,ROOT,policy=policy)
    assert first==second and audit["passed"] and audit["profiles"]==2
    manifest,checked=verify_profiles(output,history,catalog,source)
    assert checked==audit

def test_historical_cohort_contains_only_users_known_before_cutoff(profile_artifacts):
    source,catalog,history,output,policy=profile_artifacts
    _,audit=build_profiles(history,catalog,source,output,ROOT,policy=policy,cutoff_month="2025-02")
    assert audit["profiles"]==0
    _,audit=build_profiles(history,catalog,source,output,ROOT,policy=policy,cutoff_month="2025-03")
    assert audit["profiles"]==2

def test_corrupt_profiles_and_mismatched_history_are_detected(profile_artifacts):
    source,catalog,history,output,policy=profile_artifacts
    bundle,_=build_profiles(history,catalog,source,output,ROOT,policy=policy)
    file=bundle/"profiles.jsonl";original=file.read_text();file.write_text("broken")
    with pytest.raises(ValueError,match="Checksum"):verify_profiles(output,history,catalog,source)
    file.write_text(original)
    path=bundle/"manifest.json";manifest=json.loads(path.read_text());manifest["history_bundle_id"]="wrong";write_json(path,manifest)
    with pytest.raises(ValueError,match="Incompatible profile"):verify_profiles(output,history,catalog,source)

def test_rating_dictionary_policy_mismatch_fails(profile_case,policy):
    _,_,tables=profile_case
    validate_policy_scales(policy,tables)
    tables["RatingGroups"][0]["IsDeleted"]="t"
    with pytest.raises(ValueError,match="dictionary"):validate_policy_scales(policy,tables)

def test_changed_question_semantics_requires_new_review(profile_case,policy):
    _,_,tables=profile_case
    validate_policy_scales(policy,tables)
    tables["RatingGroups"][0]["Question"]="Насколько материал сложный?"
    with pytest.raises(ValueError,match="semantics"):
        validate_policy_scales(policy,tables)

def test_changed_value_question_requires_new_review(profile_case,policy):
    _,_,tables=profile_case
    tables["Ratings"][0]["Question"]="Вам понравилось?"
    with pytest.raises(ValueError,match="semantics"):
        validate_policy_scales(policy,tables)
def test_invalid_cutoff_rejected_even_without_any_users(tmp_path,policy):
    from app.data_preparation.profile_bundle import prepare_profiles
    with pytest.raises(ValueError,match="cutoff_month"):
        prepare_profiles(tmp_path,{"bundle_id":"h"},{"bundle_id":"c"},[],policy,{},"2025-99")