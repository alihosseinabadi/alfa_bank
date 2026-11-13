"""Artificial fixtures for source semantics, chronology, partitions and recovery."""
import copy
import csv
import json
from pathlib import Path
import pytest
from app.data_preparation.pipeline import build_catalog
from app.data_preparation.contracts import Material,SourceIdentity,Alias,ChildLink
from app.data_preparation.history_source import HISTORY_EXPORT_COLUMNS,read_history_table
from app.data_preparation.history_contracts import HISTORY_VERSION,Observation
from app.data_preparation.history_io import file_hash,write_json,publish_bundle,load_source,load_catalog
from app.data_preparation.history_bundle import build_history,verify_history
from app.data_preparation.history_resolution import RATING_TYPE_TABLES
from app.data_preparation.history_time import time_evidence,before_cutoff
from app.data_preparation.user_history import normalize_history
from app.data_preparation.history_audit import audit_history
from app.data_preparation.chunking import digest
from app.data_preparation.source import EXPORT_COLUMNS,read_source_table

NOON="2025-02-01 12:00:00+00"
ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def history_case(source_dir):
    materials,aliases,blocks,links,_,_=build_catalog(source_dir)
    tables={name:[] for name in HISTORY_EXPORT_COLUMNS}
    def add(name,**values):
        row={key:"" for key in HISTORY_EXPORT_COLUMNS[name]}
        row.update(values); tables[name].append(row); return row
    add("Courses",Id="course1",IsDeleted="f",IsClosed="f",LessonQuantity="1",AutoOpenNextLesson="f",PassageMode="0")
    add("Lessons",Id="l1",IsDeleted="f",IsGroup="f",RatingGroupId="scale")
    add("Articles",Id="article1",IsDeleted="f",RatingGroupId="scale")
    for name in ("Calculators","CalculatorPages"): add(name,Id="calc1",IsDeleted="f",RatingGroupId="scale")
    add("CourseLessonBindings",Id="binding1",CourseId="course1",LessonId="l1",Order="1",IsTrial="t",IsClosed="f")
    add("CourseUserBindings",Id="e1",CourseId="course1",UserId="u1",IsCompleted="f",LessonsCompleted="1",
        IsPaid="t",Created="2025-01-01 12:00:00+00",Modified=NOON,StudyingStartDate="2025-01-01 12:00:00+00",
        IsDeleted="f",Status="1",ContentAccess="10")
    add("CourseUserLessonBindings",Id="p1",CourseUserId="e1",LessonId="l1",Completed=NOON,Created=NOON)
    add("RatingGroups",Id="scale",Title="Пример шкалы",Question="Оцените",IsDeleted="f")
    for value in range(1,6): add("Ratings",Id=f"value{value}",Value=str(value),RatingGroupId="scale",IsDeleted="f")
    add("UserRatings",Id="r1",Value="5",UserId="u1",EntityId="l1",
        EntityTypeId="8b440b1a-00c3-423a-9bae-3376475eb203",Created=NOON,Modified=NOON,IsDeleted="f")
    add("UserRatings",Id="r2",Value="4",EntityId="calc1",
        EntityTypeId="7ac1c8c3-18b8-42ea-92ea-fcc10a6d496f",Created=NOON,Modified=NOON,IsDeleted="f")
    add("UserRatings",Id="r3",Value="1",UserId="u2",EntityId="calc1",
        EntityTypeId="7ac1c8c3-18b8-42ea-92ea-fcc10a6d496f",Created=NOON,Modified=NOON,IsDeleted="f")
    for number in (1,2):
        add("RatingTags",Id=f"tag{number}",Title=f"Причина {number}",IsDeleted="f",IsSystem="f")
        add("UserRatingTagsBindings",UserRatingId="r1",TagId=f"tag{number}")
    add("RatingTagBindings",RatingId="value5",TagId="tag1",Order="1")
    add("RecommendedItems",Id="article1",ItemId="course1",
        ItemTypeId="8b440b1a-00c3-423a-9bae-3376475eb203",CreatedAtUtc=NOON,Order="1")
    source={"snapshot_id":"artificial-source","extracted_at":"2026-01-01T12:00:00+00:00"}
    return tables,source,materials,aliases,links

def run(case):
    return normalize_history(*case)

def observations(data):
    return data["observations"]+data["unassigned_observations"]+data["rejected_observations"]

def get(data,identity):
    return next(o for o in observations(data) if o.source_record_id==identity)

def add_second_course(case,with_enrollment=True):
    tables,source,materials,aliases,links=case
    course=next(m for m in materials if m.item_type=="course")
    materials.append(course.model_copy(update={"material_key":"course:course2",
        "source_identities":[SourceIdentity(table="Courses",record_id="course2")]}))
    aliases.append(Alias(source_table="Courses",source_record_id="course2",material_key="course:course2",rule="test"))
    tables["Courses"].append(dict(tables["Courses"][0],Id="course2"))
    tables["CourseLessonBindings"].append(dict(tables["CourseLessonBindings"][0],Id="binding2",CourseId="course2"))
    links.append(links[0].model_copy(update={"source_record_id":"binding2","material_key":"course:course2"}))
    if with_enrollment:
        tables["CourseUserBindings"].append(dict(tables["CourseUserBindings"][0],Id="e2",CourseId="course2",StreamId="other-stream"))

def test_baseline_partitions_and_semantics(history_case):
    data=run(history_case)
    assert len(data["observations"])==4 and len(data["unassigned_observations"])==1
    assert len(observations(data))==5
    rating=get(data,"r1")
    assert rating.source_entity_table=="Lessons" and rating.material_key=="course:course1"
    assert rating.resolution_rule=="verified_user_lesson_progress"
    assert rating.rating_scale_values==[1,2,3,4,5] and len(rating.feedback_tags)==2
    assert not get(data,"r2").user_key
    assert get(data,"e1").observation_kind=="enrollment_state"
    assert not any(o.observation_kind=="purchase" for o in observations(data))
    report=audit_history(data,history_case[0],history_case[1],{"bundle_id":"catalog"},history_case[2],history_case[3],history_case[4])
    assert report["passed"]

def test_actual_parent_binding_is_required(history_case):
    history_case[0]["CourseUserLessonBindings"][0]["CourseUserId"]="missing"
    o=get(run(history_case),"p1")
    assert o.resolution_status=="rejected" and o.user_key is None
    assert "missing_parent_enrollment" in o.quality_flags

def test_membership_in_other_course_is_not_enough(history_case):
    add_second_course(history_case)
    # l1 still exists globally, but is no longer in the actual enrolled course.
    history_case[0]["CourseLessonBindings"].pop(0); history_case[4].pop(0)
    o=get(run(history_case),"p1")
    assert o.resolution_status=="rejected" and "lesson_not_in_enrolled_course" in o.quality_flags

def test_reused_lesson_is_not_duplicated_across_courses(history_case):
    add_second_course(history_case)
    history_case[0]["CourseUserLessonBindings"].clear()
    data=run(history_case)
    rating=get(data,"r1")
    assert rating.resolution_status=="accepted" and rating.material_key is None
    assert rating.lesson_id=="l1" and rating.resolution_rule=="ambiguous_user_courses"
    assert sum(o.source_record_id=="r1" for o in observations(data))==1
    assert len(data["learning_state"])==2

def test_verified_progress_disambiguates_reused_lesson(history_case):
    add_second_course(history_case)
    rating=get(run(history_case),"r1")
    assert rating.material_key=="course:course1" and rating.course_user_binding_id=="e1"

def test_missing_users_never_inferred_from_other_rows(history_case):
    row=history_case[0]["UserRatings"][0]
    row["UserId"]=""
    o=get(run(history_case),"r1")
    assert o.resolution_status=="unassigned" and o.source_user_id is None
    assert "missing_user" in o.quality_flags

def test_deleted_and_missing_user_partition_does_not_double_count(history_case):
    history_case[0]["UserRatings"][1]["IsDeleted"]="t"
    data=run(history_case)
    assert get(data,"r2").resolution_status=="rejected"
    assert len(data["unassigned_observations"])==0 and len(observations(data))==5

@pytest.mark.parametrize("mutation,expected",[
    ("scale","unknown"),("value","invalid_value"),("deleted_scale","unknown")])
def test_unknown_scales_are_not_temporal_or_profile_labels(history_case,mutation,expected):
    if mutation=="scale": history_case[0]["Lessons"][0]["RatingGroupId"]="missing"
    if mutation=="value": history_case[0]["UserRatings"][0]["Value"]="8"
    if mutation=="deleted_scale": history_case[0]["RatingGroups"][0]["IsDeleted"]="t"
    data=run(history_case); o=get(data,"r1")
    assert o.rating_scale_status==expected and not o.evaluation_eligible
    assert o not in data["profile_inputs"] and o not in data["evaluation_inputs"]

def test_unknown_entity_type_and_wrong_membership_rejected(history_case):
    row=history_case[0]["UserRatings"][0]; row["EntityTypeId"]="unknown"
    assert get(run(history_case),"r1").resolution_status=="rejected"
    row["EntityTypeId"]="8b440b1a-00c3-423a-9bae-3376475eb203"; row["EntityId"]="course1"
    assert get(run(history_case),"r1").resolution_status=="rejected"

def test_calculator_alias_and_feedback_tags_do_not_duplicate_rating(history_case):
    data=run(history_case); o=get(data,"r3")
    assert o.material_key=="calculator:calc1"
    assert sum(x.source_record_id=="r1" for x in observations(data))==1
    assert len(get(data,"r1").feedback_tags)==2

def test_deleted_or_unknown_feedback_tags_are_explicit(history_case):
    history_case[0]["RatingTags"][0]["IsDeleted"]="t"
    history_case[0]["RatingTags"].pop()
    tags=get(run(history_case),"r1").feedback_tags
    assert {x.status for x in tags}=={"deleted","unknown"}

def test_months_and_latest_rating_value_not_backdated(history_case):
    history_case[0]["UserRatings"][0]["Modified"]="2025-04-01 12:00:00+00"
    o=get(run(history_case),"r1")
    assert o.event_time==o.available_from_month=="2025-04"
    assert not before_cutoff(o,"2025-04") and before_cutoff(o,"2025-05")
    assert o.time_granularity=="month"

def test_completion_before_creation_is_flagged_not_rewritten(history_case):
    history_case[0]["CourseUserLessonBindings"][0]["Created"]="2025-03-01 12:00:00+00"
    o=get(run(history_case),"p1")
    assert o.event_time=="2025-02" and o.time_confidence=="uncertain"
    assert "completion_before_creation" in o.quality_flags and not o.evaluation_eligible

@pytest.mark.parametrize("value,flag",[("infinity","nonfinite_date"),("bad","invalid_date")])
def test_invalid_dates_and_missing_completion_are_explicit(history_case,value,flag):
    history_case[0]["CourseUserLessonBindings"][0]["Completed"]=value
    data=run(history_case); o=get(data,"p1")
    assert o.event_time is None and not o.evaluation_eligible
    assert any(flag in item for item in o.quality_flags)
    assert data["learning_state"][0].completed_lesson_ids==[]

def test_mutable_enrollment_state_is_not_a_historical_label(history_case):
    data=run(history_case)
    assert not get(data,"e1").evaluation_eligible
    assert not any(o.observation_kind=="enrollment_state" for o in data["evaluation_inputs"])

def test_unknown_access_and_paid_flag_do_not_grant_entitlements(history_case):
    state=run(history_case)["learning_state"][0]
    assert state.access_state=="unknown" and not state.entitlement_granted
    assert state.requires_access_check and state.requires_progression_check and state.next_lesson_id is None

def test_closed_course_has_no_continuation(history_case):
    history_case[0]["Courses"][0]["IsClosed"]="t"
    state=run(history_case)["learning_state"][0]
    assert state.access_state=="blocked" and not state.candidate_lesson_ids

def test_future_or_closed_lessons_are_not_candidates(history_case):
    history_case[0]["CourseUserLessonBindings"].clear()
    history_case[0]["CourseLessonBindings"][0]["ClosedUntil"]="2027-01-01 12:00:00+00"
    history_case[4][0].closed_until="2027-01-01 12:00:00+00"
    assert not run(history_case)["learning_state"][0].candidate_lesson_ids

def test_idempotence_and_duplicate_primary_keys(history_case):
    first=run(history_case); second=run(history_case)
    assert [o.model_dump() for o in observations(first)]==[o.model_dump() for o in observations(second)]
    history_case[0]["UserRatings"].append(copy.deepcopy(history_case[0]["UserRatings"][0]))
    with pytest.raises(ValueError,match="duplicate source key"): run(history_case)

def test_related_materials_are_not_personal_events(history_case):
    data=run(history_case)
    assert data["related_materials"][0].status=="resolved"
    assert data["related_materials"][0].source_material_key=="article:article1"
    assert len(observations(data))==5

def test_source_and_catalog_allowlists_are_separate():
    assert "UserRatings" not in EXPORT_COLUMNS and "UserRatings" in HISTORY_EXPORT_COLUMNS
    assert all(not({"IP","CreatedById","ModifiedById"}&set(columns)) for columns in HISTORY_EXPORT_COLUMNS.values())
    with pytest.raises(ValueError): read_history_table("Files",Path("missing"))
    with pytest.raises(ValueError): read_source_table("UserRatings",Path("missing"))

@pytest.fixture
def history_artifacts(history_case,tmp_path):
    tables,_,materials,aliases,links=history_case
    source=tmp_path/"source"; source.mkdir()
    files={}
    for name,columns in HISTORY_EXPORT_COLUMNS.items():
        path=source/(name+".csv")
        with path.open("w",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=columns); writer.writeheader(); writer.writerows(tables[name])
        files[name]={"filename":path.name,"columns":list(columns),"rows":len(tables[name]),"sha256":file_hash(path)}
    write_json(source/"manifest.json",{"snapshot_id":digest(files),"files":files,"extracted_at":"2026-01-01T12:00:00+00:00"})
    catalog=tmp_path/"catalog"
    publish_bundle(catalog,"a"*64,{"materials.jsonl":materials,"aliases.jsonl":aliases,"child_links.jsonl":links},
                   {"config":{"catalog_version":"catalog-v2"}})
    return source,catalog,tmp_path/"history"

def test_bundle_repeatability_verification_and_month_split(history_artifacts):
    source,catalog,output=history_artifacts
    first,audit=build_history(source,catalog,output,ROOT,"2025-02")
    second,_=build_history(source,catalog,output,ROOT,"2025-02")
    assert first==second
    manifest,checked=verify_history(output,source,catalog)
    assert checked==audit and checked["passed"]
    assert (first/"evaluation_before_cutoff.jsonl").read_text()==""
    assert len((first/"evaluation_from_cutoff.jsonl").read_text().splitlines())==3

def test_corrupt_artifact_detected(history_artifacts):
    source,catalog,output=history_artifacts
    bundle,_=build_history(source,catalog,output,ROOT)
    (bundle/"observations.jsonl").write_text("corrupt")
    with pytest.raises(ValueError,match="Checksum"): verify_history(output,source,catalog)

def test_incompatible_catalog_and_failed_build_preserve_current(history_artifacts):
    source,catalog,output=history_artifacts
    bundle,_=build_history(source,catalog,output,ROOT)
    current=(output/"CURRENT").read_text()
    manifest_path=catalog/("a"*64)/"manifest.json"
    manifest=json.loads(manifest_path.read_text()); manifest["config"]["catalog_version"]="wrong"
    write_json(manifest_path,manifest)
    with pytest.raises(ValueError,match="Incompatible catalog"): build_history(source,catalog,output,ROOT)
    assert (output/"CURRENT").read_text()==current

def test_catalog_link_mismatch_rejected(history_case):
    history_case[4][0].lesson_id="different"
    with pytest.raises(ValueError,match="Incompatible catalog lesson"): run(history_case)

def test_audit_detects_tampered_user_mapping(history_case):
    data=run(history_case)
    data["observations"][0].user_key="organizer:wrong"
    with pytest.raises(ValueError,match="no_inferred_users"):
        audit_history(data,history_case[0],history_case[1],{"bundle_id":"catalog"},*history_case[2:])

def test_current_progress_does_not_backdate_ambiguous_course_attribution(history_case):
    add_second_course(history_case)
    data=run(history_case)
    rating=get(data,"r1")
    assert rating.material_key=="course:course1"
    assert "temporal_course_attribution_not_verified" in rating.quality_flags
    assert not rating.evaluation_eligible and rating not in data["evaluation_inputs"]

def test_audit_detects_changed_source_rating_value(history_case):
    data=run(history_case)
    get(data,"r1").rating_value=1
    with pytest.raises(ValueError,match="rating_values_preserved"):
        audit_history(data,history_case[0],history_case[1],{"bundle_id":"catalog"},*history_case[2:])