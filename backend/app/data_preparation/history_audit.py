"""Independent partition checks and aggregate-only history acceptance report."""
from collections import Counter
from .chunking import digest
from .history_source import PRIMARY_SOURCES
from .history_time import before_cutoff

def audit_history(data,tables,source,catalog_manifest,materials,aliases,links):
    accepted=data["observations"]; unassigned=data["unassigned_observations"]; rejected=data["rejected_observations"]
    all_obs=accepted+unassigned+rejected
    checks={}
    checks["unique_observation_ids"]=len({o.observation_id for o in all_obs})==len(all_obs)
    expected={(table,row["Id"]) for table in PRIMARY_SOURCES for row in tables[table]}
    actual={(o.source_table,o.source_record_id) for o in all_obs}
    checks["all_source_rows_accounted_once"]=actual==expected and len(all_obs)==len(expected)
    checks["stable_source_identities"]=all(o.observation_id==digest([o.source_table,o.source_record_id]) for o in all_obs)
    checks["source_snapshot_parity"]=all(o.source_snapshot_id==source["snapshot_id"] and o.ingestion_time==source["extracted_at"] for o in all_obs)
    checks["exclusive_partitions"]=all(o.resolution_status=="accepted" for o in accepted) and all(
        o.resolution_status=="unassigned" for o in unassigned) and all(o.resolution_status=="rejected" for o in rejected)
    owners={m.material_key:m for m in materials}
    alias={(a.source_table,a.source_record_id):a.material_key for a in aliases}
    source_rows={name:{r["Id"]:r for r in tables[name]} for name in PRIMARY_SOURCES}
    binding=source_rows["CourseUserBindings"]
    source_users={}
    for table,rows in source_rows.items():
        for key,row in rows.items():
            source_users[(table,key)]=(binding.get(row["CourseUserId"],{}).get("UserId") if table=="CourseUserLessonBindings" else row["UserId"]) or None
    checks["raw_source_values_preserved"]=all(o.raw_values=={k:v or None for k,v in source_rows[o.source_table][o.source_record_id].items() if k not in o.raw_dates} and o.raw_dates=={k:v or None for k,v in source_rows[o.source_table][o.source_record_id].items() if k in {"Created","Modified","StudyingStartDate","Completed","BuyingDate"}} for o in all_obs)
    checks["rating_values_preserved"]=all(o.rating_value==int(source_rows["UserRatings"][o.source_record_id]["Value"]) for o in all_obs if o.source_table=="UserRatings")
    checks["no_inferred_users"]=all(o.source_user_id==source_users[(o.source_table,o.source_record_id)]
        and o.user_key==("organizer:"+o.source_user_id if o.source_user_id else None) for o in all_obs)
    checks["accepted_users_resolved"]=all(o.user_key and o.source_entity_table for o in accepted)
    checks["accepted_materials_resolved"]=all(o.material_key in owners or
        (o.material_key is None and o.source_entity_table=="Lessons") for o in accepted)
    checks["lesson_entities_exist"]=all(o.lesson_id in {r["Id"] for r in tables["Lessons"]} for o in accepted if o.lesson_id)
    child_pairs={(x.material_key,x.lesson_id) for x in links}
    checks["lesson_progress_uses_actual_enrollment"]=all(
        o.course_user_binding_id==source_rows["CourseUserLessonBindings"][o.source_record_id]["CourseUserId"]
        and o.material_key==alias.get(("Courses",binding[o.course_user_binding_id]["CourseId"]))
        and (o.material_key,o.lesson_id) in child_pairs
        for o in accepted if o.observation_kind=="lesson_progress")
    lookup={o.observation_id:o for o in accepted}
    for name in ("profile_inputs","evaluation_inputs"):
        checks[name+"_are_exact_projections"]=all(o.observation_id in lookup and
            o.model_dump()==lookup[o.observation_id].model_dump() for o in data[name]) and len({
                o.observation_id for o in data[name]})==len(data[name])
    checks["evaluation_projection_complete"]={o.observation_id for o in data["evaluation_inputs"]}=={
        o.observation_id for o in accepted if o.evaluation_eligible}
    checks["no_unverified_temporal_course_attribution"]=all("temporal_course_attribution_not_verified" not in o.quality_flags for o in data["evaluation_inputs"])
    checks["no_mutable_enrollment_temporal_labels"]=all(o.observation_kind!="enrollment_state" for o in data["evaluation_inputs"])
    checks["evaluation_timing_usable"]=all(o.time_granularity=="month" and o.time_confidence=="coarse" and
        o.available_from_month and not o.evaluation_exclusion_reasons for o in data["evaluation_inputs"])
    checks["no_archive_rewards_or_purchases"]=all(o.observation_kind in
        {"enrollment_state","lesson_progress","explicit_rating"} for o in all_obs)
    checks["no_forbidden_raw_fields"]=all(not(set(o.raw_values)&{"IP","email","CreatedById","ModifiedById"}) for o in all_obs)
    states=data["learning_state"]
    checks["one_state_per_accepted_enrollment"]={s.course_user_binding_id for s in states}=={
        o.course_user_binding_id for o in accepted if o.observation_kind=="enrollment_state"} and len({
            s.course_user_binding_id for s in states})==len(states)
    checks["no_fabricated_entitlements"]=all(not s.entitlement_granted and s.requires_access_check and
        s.requires_progression_check and s.next_lesson_id is None for s in states)
    lesson_entities={r["Id"]:r for r in tables["Lessons"]}
    checks["continuation_candidates_resolve"]=all((s.material_key,lesson) in child_pairs and
        lesson_entities[lesson]["IsDeleted"]=="f" and lesson_entities[lesson]["IsGroup"]=="f" and
        lesson not in s.completed_lesson_ids for s in states for lesson in s.candidate_lesson_ids)
    related=data["related_materials"]
    checks["all_related_rows_accounted"]=len(related)==len(tables["RecommendedItems"])==len({r.relation_id for r in related})
    checks["resolved_relations_have_valid_endpoints"]=all(
        r.source_material_key in owners and r.target_material_key in owners for r in related if r.status=="resolved")
    reconciliation={}
    for table in PRIMARY_SOURCES:
        reconciliation[table]={"source":len(tables[table]),"accepted":sum(o.source_table==table for o in accepted),
            "unassigned":sum(o.source_table==table for o in unassigned),"rejected":sum(o.source_table==table for o in rejected)}
    flags=Counter(flag for o in all_obs for flag in o.quality_flags)
    exclusions=Counter(reason for o in accepted for reason in o.evaluation_exclusion_reasons)
    months=sorted({o.available_from_month for o in data["evaluation_inputs"]})
    # Future evaluation must choose its actual cutoff. These are diagnostic counts,
    # not a tuned train/test split or a model quality claim.
    temporal_counts={month:sum(before_cutoff(o,month) for o in data["evaluation_inputs"]) for month in months}
    report={"passed":all(checks.values()),"checks":checks,"source_reconciliation":reconciliation,
        "total_source_observations":len(all_obs),"accepted":len(accepted),"unassigned":len(unassigned),"rejected":len(rejected),
        "accepted_users":len({o.user_key for o in accepted}),"profile_inputs":len(data["profile_inputs"]),
        "evaluation_inputs":len(data["evaluation_inputs"]),
        "evaluation_share_of_accepted":len(data["evaluation_inputs"])/len(accepted) if accepted else 0,
        "evaluation_by_kind":dict(Counter(o.observation_kind for o in data["evaluation_inputs"])),
        "time_confidence":dict(Counter(o.time_confidence for o in all_obs)),
        "quality_flags":dict(flags),"evaluation_exclusions":dict(exclusions),
        "rating_scale_status":dict(Counter(o.rating_scale_status for o in all_obs if o.observation_kind=="explicit_rating")),
        "lesson_rating_resolution":dict(Counter(o.resolution_rule for o in all_obs if
            o.observation_kind=="explicit_rating" and o.source_entity_table=="Lessons")),
        "learning_states":len(states),"states_with_candidates":sum(bool(s.candidate_lesson_ids) for s in states),
        "continuation_quality_flags":dict(Counter(flag for s in states for flag in s.quality_flags)),
        "related_materials_status":dict(Counter(r.status for r in related)),
        "supporting":data["supporting_audit"],"temporal_counts_strictly_before_month":temporal_counts,
        "catalog_bundle_id":catalog_manifest["bundle_id"],"history_snapshot_id":source["snapshot_id"],
        "limitations":["Archive states are not recommendation exposures or verified purchases.",
            "Month-level availability is a conservative projection, not a precise clickstream.",
            "The current catalog cannot reconstruct historical content or access.",
            "Unknown access/sequence enums are preserved; runtime platform checks remain required.",
            "Unassigned ratings are excluded from personal profiles; IDs are pseudonymous, not anonymous."]}
    if not report["passed"]:
        raise ValueError("History acceptance failed: "+str([k for k,v in checks.items() if not v]))
    return report
