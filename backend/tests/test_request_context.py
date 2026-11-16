"""Case-aligned MVP request scenarios; no actual organizer data is printed."""
import copy
from pathlib import Path
import importlib.util
import pytest
from test_user_profiles import profile_case,policy,build
from test_history_stage3 import history_case
from app.ml.request_context import build_request_context
from app.ml.profile_contracts import ExplicitConstraints,ExplicitPreferences
from app.ml.user_profile import build_user_profile
from app.data_preparation.learning_state import build_learning_state
from app.data_preparation.history_contracts import LearningState

def test_explicit_task_wins_without_mutating_profile(profile_case,policy):
    p=build(profile_case,policy);before=p.model_dump()
    task="  Нужен шаблон договора для маркетинга  "
    context=build_request_context(p,task)
    assert context.task_text==task and context.query_text==task.strip()
    assert context.query_source=="explicit_task" and context.history_weight==0
    assert "Финансы" not in context.query_text
    another=build_request_context(p,"Как нанимать людей?")
    assert another.query_text!=context.query_text and another.profile_version==context.profile_version
    assert p.model_dump()==before

def test_explicit_formats_time_and_onboarding_have_precedence(profile_case,policy):
    prefs=ExplicitPreferences(formats=["course"],available_time_minutes=60,industry="retail",business_stage="starting",experience="new")
    p=build(profile_case,policy,explicit_preferences=prefs)
    ctx=build_request_context(p,"Задача",ExplicitConstraints(formats=["document"],available_time_minutes=10))
    assert ctx.formats==["document"] and ctx.available_time_minutes==10
    assert ctx.industry=="retail" and ctx.business_stage=="starting" and ctx.experience=="new"
    assert build_request_context(p,"Задача",ExplicitConstraints(formats=[])).formats==[]
    assert p.explicit_preferences.formats==["course"]

def test_no_history_formats_are_inferred(profile_case,policy):
    p=build(profile_case,policy)
    assert p.observed_format_counts=={"course":1}
    ctx=build_request_context(p)
    assert ctx.formats==[] and ctx.available_time_minutes is None and ctx.budget_preference is None

def test_unknown_user_task_and_no_task(profile_case,policy):
    _,materials,_=profile_case
    p=build_user_profile("organizer:new",[],materials,policy=policy)
    with_task=build_request_context(p,"Как продвигать бизнес?")
    assert with_task.cold_start and not with_task.fallback_required
    empty=build_request_context(p)
    assert empty.cold_start and empty.fallback_required and empty.clarification
    assert empty.query_strategy=="starter_required"

def test_optional_onboarding_topics_work_without_history(profile_case,policy):
    _,materials,_=profile_case
    p=build_user_profile("organizer:new",[],materials,ExplicitPreferences(selected_topics=["Продажи"],formats=["article"]),policy)
    context=build_request_context(p)
    assert context.query_source=="explicit_topics" and context.query_text=="Продажи"
    assert context.cold_start and not context.fallback_required
    assert context.formats==["article"]

def test_negative_topics_are_soft_evidence_not_query(profile_case,policy):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    p=build(profile_case,policy,items=[grade.model_copy(update={"rating_value":1})])
    ctx=build_request_context(p,"Другая задача")
    assert ctx.avoidance_topics==[] and ctx.query_text=="Другая задача"
    assert ctx.history_weight==0

def synthetic_state():
    return LearningState(user_key="organizer:u1",course_user_binding_id="e1",material_key="course:course1",
        stream_id=None,subscription_id=None,is_completed=False,completed_lesson_ids=[],active_leaf_lesson_count=2,
        source_lessons_completed=0,candidate_lesson_ids=["lesson-next"],access_state="unknown",
        quality_flags=[],as_of="2026-01-01T12:00:00+00:00")

def test_continuation_keeps_unknown_access_and_never_invents_url(profile_case,policy):
    p=build(profile_case,policy);state=synthetic_state();before=state.model_dump()
    ctx=build_request_context(p,learning_state=[state])
    candidate=ctx.continuation_candidates[0]
    assert candidate.requires_access_check and candidate.requires_progression_check
    assert not candidate.entitlement_granted
    assert "url" not in candidate.model_dump() and "next_lesson_id" not in candidate.model_dump()
    assert state.model_dump()==before

@pytest.mark.parametrize("changes",[{"access_state":"blocked"},{"is_completed":True},{"user_key":"organizer:other"},{"candidate_lesson_ids":[]}])
def test_unsuitable_continuation_is_not_forwarded(profile_case,policy,changes):
    ctx=build_request_context(build(profile_case,policy),learning_state=[synthetic_state().model_copy(update=changes)])
    assert not ctx.continuation_candidates

def test_historical_context_ignores_current_state_but_interest_reset_keeps_progress(profile_case,policy):
    historical=build(profile_case,policy,cutoff_month="2025-03")
    assert not build_request_context(historical,learning_state=[synthetic_state()]).continuation_candidates
    reset=build(profile_case,policy,explicit_preferences=ExplicitPreferences(reset_inferred=True))
    assert build_request_context(reset,learning_state=[synthetic_state()]).continuation_candidates

def test_synthetic_cli_cases_are_public_and_cover_case_scenarios():
    root=Path(__file__).resolve().parents[2]
    spec=importlib.util.spec_from_file_location("inspect_context",root/"scripts/inspect_user_context.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.run_demo()
    assert len(result)==8 and all(row["synthetic"] for row in result)
    by={row["scenario"]:row for row in result}
    assert by["new_user_with_task"]["query_source"]=="explicit_task"
    assert by["many_lessons_one_course"]["topic_weights"]=={"Маркетинг":0.5,"Финансы":0.5}
    assert by["negative_rating"]["topic_weights"]=={}
    assert by["task_switch"]["history_weight"]==0
    assert by["unknown_user_no_task"]["fallback_required"]

def test_policy_topic_limit_reaches_request_context(profile_case,policy):
    data,materials,_=profile_case
    materials=[m.model_copy(update={"topics":["Один","Два","Три"]}) if m.item_type=="course" else m for m in materials]
    policy=policy.model_copy(update={"max_context_topics":1})
    p=build_user_profile("organizer:u1",data["profile_inputs"],materials,policy=policy)
    ctx=build_request_context(p)
    assert p.context_topic_limit==1 and len(ctx.supporting_interests)==1

def test_explicit_task_clears_both_positive_and_negative_history_cues(profile_case,policy):
    data,_,_=profile_case
    grade=next(o for o in data["profile_inputs"] if o.source_record_id=="r1")
    p=build(profile_case,policy,items=[grade.model_copy(update={"rating_value":1})])
    ctx=build_request_context(p,"Хочу изучить финансы")
    assert ctx.query_text=="Хочу изучить финансы" and ctx.history_weight==0
    assert ctx.supporting_interests==[] and ctx.avoidance_topics==[]
    assert not ctx.avoidance_is_hard_filter