"""Normalize archive states without fabricating exposures or purchases."""
from collections import Counter, defaultdict
from .chunking import digest
from .history_contracts import Observation, FeedbackTag
from .history_source import HISTORY_EXPORT_COLUMNS, PRIMARY_SOURCES
from .history_time import time_evidence
from .history_resolution import HistoryResolver, related_materials
from .learning_state import build_learning_state

COMPOSITE_KEYS={"UserRatingTagsBindings":("UserRatingId","TagId"),
                "RatingTagBindings":("RatingId","TagId"),
                "RecommendedItems":("Id","ItemId","ItemTypeId")}

def validate_tables(tables):
    if set(tables)!=set(HISTORY_EXPORT_COLUMNS):
        raise ValueError("Unexpected/missing history source tables")
    for name,rows in tables.items():
        key=COMPOSITE_KEYS.get(name,("Id",))
        identities=set()
        for row in rows:
            if set(row)!=set(HISTORY_EXPORT_COLUMNS[name]):
                raise ValueError(f"Wrong columns: {name}")
            identity=tuple(row[k] for k in key)
            if any(not value for value in identity) or identity in identities:
                raise ValueError(f"Empty/duplicate source key: {name}")
            identities.add(identity)
        if name=="CourseLessonBindings":
            if len({(r["CourseId"],r["LessonId"]) for r in rows})!=len(rows):
                raise ValueError("Duplicate course/lesson source relation")

def validate_catalog_support(tables,materials,aliases,links):
    lookup={(a.source_table,a.source_record_id):a.material_key for a in aliases}
    if len({m.material_key for m in materials})!=len(materials):
        raise ValueError("Duplicate catalog material")
    owners={m.material_key for m in materials}
    if any(a.material_key not in owners for a in aliases):
        raise ValueError("Orphan catalog alias")
    for source in ("Courses","Articles","Calculators","CalculatorPages"):
        source_ids={r["Id"] for r in tables[source]}
        catalog_ids={a.source_record_id for a in aliases if a.source_table==source}
        if source_ids!=catalog_ids:
            raise ValueError(f"Incompatible catalog source identities: {source}")
    expected={}
    for row in tables["CourseLessonBindings"]:
        key=lookup.get(("Courses",row["CourseId"]))
        if key is None:
            raise ValueError("History course not in pinned catalog")
        expected[row["Id"]]=(key,row["LessonId"],int(row["Order"] or 0),
                            row["IsClosed"]=="t" if row["IsClosed"] else None,
                            row["IsTrial"]=="t" if row["IsTrial"] else None,row["ClosedUntil"] or None)
    actual={x.source_record_id:(x.material_key,x.lesson_id,x.order,x.is_closed,x.is_trial,x.closed_until) for x in links}
    if expected!=actual:
        raise ValueError("Incompatible catalog lesson links")

def normalize_history(tables,source_manifest,materials,aliases,links):
    validate_tables(tables)
    validate_catalog_support(tables,materials,aliases,links)
    resolver=HistoryResolver(tables,materials,aliases,links)
    groups={r["Id"]:r for r in tables["RatingGroups"]}
    scales=defaultdict(set)
    for row in tables["Ratings"]:
        group=groups.get(row["RatingGroupId"])
        if row["IsDeleted"]=="f" and group and group["IsDeleted"]=="f":
            scales[row["RatingGroupId"]].add(int(row["Value"]))
    tag_lookup={r["Id"]:r for r in tables["RatingTags"]}
    rating_ids={r["Id"] for r in tables["UserRatings"]}
    tag_links=defaultdict(list)
    tag_audit=Counter()
    for row in tables["UserRatingTagsBindings"]:
        if row["UserRatingId"] not in rating_ids:
            tag_audit["orphan_rating"]+=1
            continue
        tag=tag_lookup.get(row["TagId"])
        state="unknown" if not tag else "deleted" if tag["IsDeleted"]=="t" else "resolved"
        tag_audit[state]+=1
        tag_links[row["UserRatingId"]].append(FeedbackTag(tag_id=row["TagId"],
            label=tag["Title"] if state=="resolved" else None,text=row["Text"] or None,status=state))
    accepted,unassigned,rejected=[],[],[]
    source_id=source_manifest["snapshot_id"]
    ingestion=source_manifest["extracted_at"]
    def finish(row,table,kind,user,entity_table,entity_id,material_key=None,lesson_id=None,binding=None,
               flags=None,rule="unresolved",extra=None):
        timing=time_evidence(kind,row)
        all_flags=list(flags or [])+timing.pop("quality_flags")
        reason_flags=set(all_flags)
        # Missing user is not inferred from author/IP. Deleted or unresolved
        # entities are rejected; otherwise valid anonymous ratings are unassigned.
        fatal={"deleted_record","deleted_entity","deleted_enrollment","missing_parent_enrollment",
               "missing_source_entity","missing_catalog_alias","lesson_not_in_enrolled_course",
               "unsupported_entity_type","entity_id_not_in_declared_context","group_not_learning_lesson"}
        state="rejected" if reason_flags & fatal else "unassigned" if not user else "accepted"
        if not user:
            all_flags.append("missing_user")
        if reason_flags & {"rating_scale_unknown", "rating_scale_invalid_value"}:
            timing["evaluation_eligible"]=False
            timing["available_from_month"]=None
            timing["evaluation_exclusion_reasons"]+=["unresolved_rating_scale"]
        if "temporal_course_attribution_not_verified" in reason_flags:
            timing["evaluation_eligible"]=False
            timing["available_from_month"]=None
            timing["evaluation_exclusion_reasons"]+=["temporal_course_attribution_not_verified"]
        if state!="accepted":
            timing["evaluation_eligible"]=False
            timing["available_from_month"]=None
            timing["evaluation_exclusion_reasons"]+=["not_personal_accepted_observation"]
        obs=Observation(observation_id=digest([table,row["Id"]]),source_table=table,
            source_record_id=row["Id"],source_snapshot_id=source_id,source_user_id=user or None,
            user_key="organizer:"+user if user else None,observation_kind=kind,
            source_entity_table=entity_table,source_entity_id=entity_id,
            source_entity_type_id=row.get("EntityTypeId") or None,material_key=material_key,
            lesson_id=lesson_id,course_user_binding_id=binding,ingestion_time=ingestion,
            resolution_status=state,resolution_rule=rule,quality_flags=sorted(set(all_flags)),
            raw_values={k:v or None for k,v in row.items() if k not in timing["raw_dates"]},
            **timing,**(extra or {}))
        {"accepted":accepted,"unassigned":unassigned,"rejected":rejected}[state].append(obs)
        return obs

    for row in tables["CourseUserBindings"]:
        entity=resolver.entities["Courses"].get(row["CourseId"])
        key=resolver.aliases.get(("Courses",row["CourseId"]))
        flags=[]
        if row["IsDeleted"]=="t": flags.append("deleted_record")
        if entity is None: flags.append("missing_source_entity")
        elif entity["IsDeleted"]=="t": flags.append("deleted_entity")
        if not key: flags.append("missing_catalog_alias")
        finish(row,"CourseUserBindings","enrollment_state",row["UserId"],
               "Courses" if entity else None,row["CourseId"],key,binding=row["Id"],flags=flags,
               rule="verified_course_alias")

    for row in tables["CourseUserLessonBindings"]:
        parent=resolver.bindings.get(row["CourseUserId"])
        entity=resolver.entities["Lessons"].get(row["LessonId"])
        key=resolver.aliases.get(("Courses",parent["CourseId"])) if parent else None
        flags=[]
        if parent is None: flags.append("missing_parent_enrollment")
        elif parent["IsDeleted"]=="t": flags.append("deleted_enrollment")
        elif resolver.entities["Courses"].get(parent["CourseId"],{}).get("IsDeleted")=="t": flags.append("deleted_entity")
        if not entity: flags.append("missing_source_entity")
        elif entity["IsDeleted"]=="t": flags.append("deleted_entity")
        elif entity["IsGroup"]=="t": flags.append("group_not_learning_lesson")
        if parent and row["LessonId"] not in resolver.course_lessons.get(key,set()):
            flags.append("lesson_not_in_enrolled_course")
        if not key: flags.append("missing_catalog_alias")
        finish(row,"CourseUserLessonBindings","lesson_progress",parent["UserId"] if parent else None,
            "Lessons" if entity else None,row["LessonId"],key,lesson_id=row["LessonId"],
            binding=row["CourseUserId"],flags=flags,rule="CourseUserId_to_enrollment_to_course")

    for row in tables["UserRatings"]:
        table,entity,key,binding,rule=resolver.resolve_rating(row)
        flags=[]
        if row["IsDeleted"]=="t": flags.append("deleted_record")
        if entity is None: flags.append(rule if rule in {"unsupported_entity_type","entity_id_not_in_declared_context"} else "missing_source_entity")
        elif entity["IsDeleted"]=="t": flags.append("deleted_entity")
        if table=="Lessons" and entity and entity["IsGroup"]=="t": flags.append("group_not_learning_lesson")
        if entity and not key:
            flags.append(rule if table=="Lessons" else "missing_catalog_alias")
        if table=="Lessons" and key and len(resolver.lesson_courses.get(row["EntityId"],set()))>1:
            flags.append("temporal_course_attribution_not_verified")
        group_id=entity.get("RatingGroupId") or None if entity else None
        values=sorted(scales.get(group_id,set()))
        scale_state="unknown" if not values else "resolved" if int(row["Value"]) in values else "invalid_value"
        if scale_state!="resolved": flags.append("rating_scale_"+scale_state)
        finish(row,"UserRatings","explicit_rating",row["UserId"],table if entity else None,row["EntityId"],
            key,lesson_id=row["EntityId"] if table=="Lessons" else None,binding=binding,flags=flags,rule=rule,
            extra=dict(rating_value=int(row["Value"]),rating_group_id=group_id,
                rating_scale_values=values,rating_scale_status=scale_state,
                feedback_tags=sorted(tag_links[row["Id"]],key=lambda x:x.tag_id)))

    accepted.sort(key=lambda x:x.observation_id)
    unassigned.sort(key=lambda x:x.observation_id)
    rejected.sort(key=lambda x:x.observation_id)
    # Keep source counter snapshots for learning_state, not as a separate
    # weighted positive signal in profile inputs.
    profile=[o for o in accepted if o.observation_kind!="explicit_rating" or o.rating_scale_status=="resolved"]
    evaluation=[o for o in accepted if o.evaluation_eligible]
    states=build_learning_state(accepted,tables,aliases,links,ingestion)
    related=related_materials(tables["RecommendedItems"],materials,aliases)
    return dict(observations=accepted,unassigned_observations=unassigned,rejected_observations=rejected,
                profile_inputs=profile,evaluation_inputs=evaluation,learning_state=states,related_materials=related,
                supporting_audit={"rating_tag_links":dict(tag_audit)})
