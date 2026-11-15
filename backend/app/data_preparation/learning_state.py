"""Snapshot continuation candidates; never grant platform access."""
from collections import defaultdict
from .history_contracts import LearningState
from .history_time import parse_date

def build_learning_state(observations,tables,aliases,links,as_of):
    course_entities={r["Id"]:r for r in tables["Courses"]}
    lessons={r["Id"]:r for r in tables["Lessons"]}
    course_lookup={a.material_key:a.source_record_id for a in aliases if a.source_table=="Courses"}
    by_course=defaultdict(list)
    for link in links:
        if link.lesson_id in lessons and lessons[link.lesson_id]["IsDeleted"]=="f" and lessons[link.lesson_id]["IsGroup"]=="f":
            by_course[link.material_key].append(link)
    progress=defaultdict(set)
    for o in observations:
        if o.observation_kind=="lesson_progress" and o.raw_dates.get("Completed"):
            completed,error=parse_date(o.raw_dates["Completed"])
            if completed is not None and not error:
                progress[o.course_user_binding_id].add(o.lesson_id)
    now,_=parse_date(as_of)
    result=[]
    for o in observations:
        if o.observation_kind!="enrollment_state":
            continue
        source=o.raw_values
        course=course_entities[course_lookup[o.material_key]]
        leaves=sorted(by_course[o.material_key],key=lambda x:(x.order,x.lesson_id))
        done=sorted(progress[o.course_user_binding_id])
        flags=[]
        if len(done)!=int(source["LessonsCompleted"]):
            flags.append("progress_counter_mismatch")
        completed=source["IsCompleted"]=="t"
        blocked=course["IsClosed"]=="t"
        candidates=[]
        for link in leaves:
            if link.lesson_id in done or link.is_closed is True:
                continue
            until,error=parse_date(link.closed_until)
            if error:
                flags.append("invalid_lesson_opening_date")
                continue
            if until and now and until>now:
                continue
            candidates.append(link.lesson_id)
        if completed or blocked:
            candidates=[]
        if not completed and not candidates:
            flags.append("no_verified_unfinished_candidate")
        result.append(LearningState(user_key=o.user_key,course_user_binding_id=o.course_user_binding_id,
            material_key=o.material_key,stream_id=source.get("StreamId") or None,
            subscription_id=source.get("SubscriptionId") or None,is_completed=completed,
            completed_lesson_ids=done,active_leaf_lesson_count=len(leaves),
            source_lessons_completed=int(source["LessonsCompleted"]),candidate_lesson_ids=candidates[:5],
            next_lesson_id=None,access_state="blocked" if blocked else "unknown",
            quality_flags=sorted(set(flags+["platform_access_and_sequence_not_verified"])),as_of=as_of))
    return sorted(result,key=lambda x:x.course_user_binding_id)
