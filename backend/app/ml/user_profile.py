"""Deterministic, capped per-material interests for a small recommender MVP."""
from collections import Counter,defaultdict
import re
from .profile_contracts import UserProfile,ExplicitPreferences,MaterialEvidence,TopicEvidence,TitleFallback
from .profile_policy import ProfilePolicy,default_policy,rating_polarity,fingerprint

def _normalized(values):
    total=sum(values.values())
    return {key:value/total for key,value in sorted(values.items()) if value>0} if total else {}

def _before_cutoff(observation,cutoff):
    # Pure counterpart of the stage-3 gate; adapter validates its input projection.
    return bool(observation.evaluation_eligible and observation.time_confidence=="coarse" and
                observation.available_from_month and observation.available_from_month<cutoff and
                observation.observation_kind!="enrollment_state" and
                "temporal_course_attribution_not_verified" not in observation.quality_flags)

def build_user_profile(user_key,observations,materials,explicit_preferences=None,policy=None,*,
                       history_bundle_id="unbound",catalog_bundle_id="unbound",cutoff_month=None):
    policy=policy or default_policy()
    explicit=(explicit_preferences or ExplicitPreferences()).model_copy(deep=True)
    if cutoff_month is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",cutoff_month):
        raise ValueError("cutoff_month must be YYYY-MM")
    if not user_key or not isinstance(user_key,str):
        raise ValueError("user_key is required")
    owners={m.material_key:m for m in materials}
    if len(owners)!=len(materials):raise ValueError("Duplicate material key")
    by_material=defaultdict(list); seen={}; skipped=Counter()
    reset=explicit.reset_inferred
    for observation in observations:
        if observation.user_key!=user_key:
            continue
        # A duplicate with different contents is an error, not arbitrary first/last wins.
        signature=fingerprint(observation.model_dump())
        if observation.observation_id in seen:
            if seen[observation.observation_id]!=signature:raise ValueError("Conflicting observation identity")
            continue
        seen[observation.observation_id]=signature
        if observation.resolution_status!="accepted" or not observation.source_user_id:
            skipped["not_accepted_personal_observation"]+=1;continue
        if user_key!="organizer:"+observation.source_user_id:
            skipped["identity_namespace_mismatch"]+=1;continue
        if cutoff_month and not _before_cutoff(observation,cutoff_month):
            skipped["not_available_before_cutoff"]+=1;continue

        if reset:
            skipped["inferred_preferences_reset"]+=1;continue
        if observation.material_key is None:
            skipped["ambiguous_material"]+=1;continue
        if observation.material_key not in owners:
            raise ValueError("Observation material missing from pinned catalog")
        if observation.observation_kind=="explicit_rating" and rating_polarity(observation,policy) is None:
            skipped["unreviewed_or_unknown_rating_scale"]+=1;continue
        by_material[observation.material_key].append(observation)
    material_evidence=[]; positive=defaultdict(float); negative=defaultdict(float)
    support=defaultdict(set); negative_support=defaultdict(set); formats=Counter(); titles=[]
    for key,items in sorted(by_material.items()):
        implicit=positive_rating=negative_rating=0.0
        source_kinds=set()
        for o in items:
            source_kinds.add(o.observation_kind)
            if o.observation_kind=="enrollment_state":
                implicit=max(implicit,policy.enrollment_strength)
            elif o.observation_kind=="lesson_progress" and o.raw_dates.get("Completed") and o.event_time:
                implicit=max(implicit,policy.completion_strength)
            elif o.observation_kind=="explicit_rating":
                polarity=rating_polarity(o,policy)
                if polarity=="positive":positive_rating=max(positive_rating,policy.positive_rating_strength)
                elif polarity=="negative":negative_rating=max(negative_rating,policy.negative_rating_strength)
        pos=max(implicit,positive_rating); neg=negative_rating; net=max(pos-neg,0.0)
        material=owners[key];formats[material.item_type]+=1
        material_evidence.append(MaterialEvidence(material_key=key,implicit_strength=implicit,
            explicit_positive=positive_rating,explicit_negative=negative_rating,
            positive_strength=pos,negative_strength=neg,net_strength=net,
            source_kinds=sorted(source_kinds),observation_ids=sorted(o.observation_id for o in items)))
        topics=sorted(set(topic.strip() for topic in material.topics if topic.strip()))
        if not topics:
            skipped["material_without_topics"]+=1
        for topic in topics:
            # Divide one bounded material contribution across its source labels.
            positive[topic]+=pos/len(topics);negative[topic]+=neg/len(topics)
            if pos>0:support[topic].add(key)
            if neg>0:negative_support[topic].add(key)
        # A negative rating cannot become positive title fallback.
        if net>0 and not topics and material.is_discoverable and material.url_state!="unavailable" and material.title:
            titles.append(TitleFallback(material_key=key,title=material.title,evidence_strength=net))
    topic_weights=_normalized({topic:max(positive[topic]-negative[topic],0.0) for topic in positive})
    avoidance_weights=_normalized(negative)
    evidence=[]
    for topic in sorted(set(positive)|set(negative)):
        keys=support[topic]|negative_support[topic]; n=len(keys)
        strength=positive[topic]+negative[topic]
        consistency=abs(positive[topic]-negative[topic])/strength if strength else 0.0
        evidence.append(TopicEvidence(topic=topic,positive_strength=positive[topic],negative_strength=negative[topic],
            net_strength=max(positive[topic]-negative[topic],0.0),supporting_material_keys=sorted(support[topic]),
            negative_material_keys=sorted(negative_support[topic]),support_count=n,
            confidence=n/(n+policy.confidence_prior_materials)*consistency))
    titles=sorted(titles,key=lambda t:(-t.evidence_strength,t.material_key))[:policy.max_title_fallbacks]
    cold=not topic_weights and not titles
    flags=["observed_formats_are_not_preferences","confidence_is_heuristic_not_calibrated","negative_feedback_is_not_proven_topic_dislike"]
    if cutoff_month:flags.append("current_catalog_used_for_historical_projection")
    if reset:flags.append("inferred_preferences_reset")
    if skipped["ambiguous_material"]:flags.append("unresolved_lesson_evidence_skipped")
    if not material_evidence:reason="no_usable_history"
    elif cold:reason="no_positive_topic_or_title_evidence"
    else:reason=None
    values=dict(user_key=user_key,policy_version=policy.version,policy_hash=policy.identity(),
        history_bundle_id=history_bundle_id,catalog_bundle_id=catalog_bundle_id,
        mode="historical" if cutoff_month else "current",cutoff_month=cutoff_month,
        context_topic_limit=policy.max_context_topics,explicit_preferences=explicit,topic_weights=topic_weights,avoidance_weights=avoidance_weights,
        topic_evidence=evidence,material_evidence=material_evidence,title_fallbacks=titles,
        observed_format_counts=dict(sorted(formats.items())),
        support_material_count=len([m for m in material_evidence if m.positive_strength or m.negative_strength]),
        cold_start=cold,cold_start_reason=reason,quality_flags=sorted(set(flags)),skipped_observations=dict(sorted(skipped.items())),
        learning_state_reference=history_bundle_id+"/learning_state.jsonl" if not cutoff_month else None)
    identity=fingerprint({k:v.model_dump() if hasattr(v,"model_dump") else [
        x.model_dump() if hasattr(x,"model_dump") else x for x in v] if isinstance(v,list) else v for k,v in values.items()})
    return UserProfile(profile_version=identity,**values)
