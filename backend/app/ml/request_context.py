"""Task-first request context; profile and input history are never mutated."""
from .profile_contracts import RequestContext,ExplicitConstraints,ContinuationCandidate
from .profile_policy import fingerprint

def build_request_context(profile,task="",explicit_constraints=None,learning_state=(),*,max_topics=None):
    max_topics=profile.context_topic_limit if max_topics is None else max_topics
    if not isinstance(task,str):raise ValueError("task must be text")
    if not 1<=max_topics<=10:raise ValueError("Invalid supporting-topic limit")
    constraints=explicit_constraints or ExplicitConstraints()
    prefs=profile.explicit_preferences
    interests=[key for key,_ in sorted(profile.topic_weights.items(),key=lambda pair:(-pair[1],pair[0]))][:max_topics]
    avoid=[key for key,_ in sorted(profile.avoidance_weights.items(),key=lambda pair:(-pair[1],pair[0]))][:max_topics]
    explicit_topics=list(prefs.selected_topics)[:max_topics]
    if task.strip():query,source,strategy=task.strip(),"explicit_task","task_first"
    elif explicit_topics:query,source,strategy=" ".join(explicit_topics),"explicit_topics","explicit_topics_first"
    elif interests:query,source,strategy=" ".join(interests),"inferred_topics","profile_fallback"
    elif profile.title_fallbacks:query,source,strategy=" ".join(t.title for t in profile.title_fallbacks),"material_titles","profile_fallback"
    else:query,source,strategy="","cold_start","starter_required"
    candidates=[]
    if profile.mode=="current":
        for state in learning_state:
            if state.user_key!=profile.user_key or state.access_state=="blocked" or state.is_completed or not state.candidate_lesson_ids:
                continue
            candidates.append(ContinuationCandidate(material_key=state.material_key,
                course_user_binding_id=state.course_user_binding_id,candidate_lesson_ids=list(state.candidate_lesson_ids)))
    candidates=sorted(candidates,key=lambda x:(x.material_key,x.course_user_binding_id))
    if source in {"explicit_task","explicit_topics"}:
        interests,avoid=[],[]
    fallback=not query
    reasons=[source,"task_overrides_history" if task.strip() else "history_is_fallback",
             "no_inferred_format_preference"]
    if candidates:reasons.append("continuation_requires_platform_checks")
    if profile.mode=="historical":reasons.append("current_learning_state_excluded")
    values=dict(profile_version=profile.profile_version,user_key=profile.user_key,task_text=task,query_text=query,
        query_source=source,query_strategy=strategy,supporting_interests=interests,avoidance_topics=avoid,
        history_weight=0.0 if source in {"explicit_task","explicit_topics","cold_start"} else 1.0,
        formats=list(constraints.formats if constraints.formats is not None else prefs.formats),
        available_time_minutes=constraints.available_time_minutes if constraints.available_time_minutes is not None else prefs.available_time_minutes,
        budget_preference=constraints.budget_preference if constraints.budget_preference is not None else prefs.budget_preference,
        business_stage=prefs.business_stage,industry=prefs.industry,experience=prefs.experience,
        cold_start=profile.cold_start,fallback_required=fallback,
        clarification="Какую задачу бизнеса вы хотите решить?" if fallback else None,
        reason_codes=reasons,continuation_candidates=candidates,mode=profile.mode,cutoff_month=profile.cutoff_month)
    canonical={k:[x.model_dump() if hasattr(x,"model_dump") else x for x in v] if isinstance(v,list) else v for k,v in values.items()}
    return RequestContext(context_id=fingerprint(canonical),**values)
