"""Context-specific polymorphic resolution; no ID-only joins for ratings."""
from collections import defaultdict
from .chunking import digest
from .history_contracts import RelatedMaterial

RATING_TYPE_TABLES={
    "8b440b1a-00c3-423a-9bae-3376475eb203":"Lessons",
    "7ac1c8c3-18b8-42ea-92ea-fcc10a6d496f":"CalculatorPages",
    "72dfaf58-4e43-4b92-a1cd-5f8b5de739b4":"Calculators",
    "8ede4179-0faf-407d-a4fc-1d94f9a63089":"Articles",
}
TARGET_TYPE_TABLES={
    "8b440b1a-00c3-423a-9bae-3376475eb203":"Courses",
    "8ede4179-0faf-407d-a4fc-1d94f9a63089":"Articles",
    "da1ad865-8605-4ab1-9f6c-4489a26fbc35":"Documents",
    "ece4acf3-5dd3-47b9-9f08-99c0d6203cc7":"Webinars",
    "142c23e2-bf71-4a73-b12e-6b1b5e4d47cc":"Podcasts",
    "7ac1c8c3-18b8-42ea-92ea-fcc10a6d496f":"CalculatorPages",
    "72dfaf58-4e43-4b92-a1cd-5f8b5de739b4":"Calculators",
}

class HistoryResolver:
    def __init__(self,tables,materials,aliases,links):
        self.tables=tables
        self.materials={m.material_key:m for m in materials}
        self.aliases={(a.source_table,a.source_record_id):a.material_key for a in aliases}
        if len(self.aliases)!=len(aliases):
            raise ValueError("Duplicate catalog alias")
        self.entities={name:{r["Id"]:r for r in tables[name]} for name in ("Lessons","Courses","Calculators","CalculatorPages","Articles")}
        self.bindings={r["Id"]:r for r in tables["CourseUserBindings"]}
        self.course_lessons=defaultdict(set)
        self.lesson_courses=defaultdict(set)
        for link in links:
            self.course_lessons[link.material_key].add(link.lesson_id)
            self.lesson_courses[link.lesson_id].add(link.material_key)
        self.user_bindings=defaultdict(list)
        for b in self.bindings.values():
            if b["UserId"] and b["IsDeleted"]=="f" and self.aliases.get(("Courses",b["CourseId"])):
                self.user_bindings[b["UserId"]].append(b)
        self.progress=defaultdict(list)
        for p in tables["CourseUserLessonBindings"]:
            b=self.bindings.get(p["CourseUserId"])
            if b and b["IsDeleted"]=="f":
                key=self.aliases.get(("Courses",b["CourseId"]))
                if p["LessonId"] in self.course_lessons.get(key,set()):
                    self.progress[(b["UserId"],p["LessonId"])].append(b)

    def lesson_course(self,lesson_id,user_id):
        progress=self.progress.get((user_id,lesson_id),[])
        candidates=progress or [b for b in self.user_bindings.get(user_id,[])
            if lesson_id in self.course_lessons[self.aliases[("Courses",b["CourseId"])]]]
        keys={self.aliases[("Courses",b["CourseId"])] for b in candidates}
        if len(keys)==1:
            return next(iter(keys)),candidates[0]["Id"] if len(candidates)==1 else None,(
                "verified_user_lesson_progress" if progress else "verified_user_enrollment")
        if len(keys)>1:
            return None,None,"ambiguous_user_courses"
        global_keys=self.lesson_courses.get(lesson_id,set())
        if len(global_keys)==1:
            return next(iter(global_keys)),None,"unique_catalog_lesson_course"
        return None,None,"ambiguous_lesson_courses" if global_keys else "lesson_without_catalog_course"

    def resolve_rating(self,row):
        table=RATING_TYPE_TABLES.get(row["EntityTypeId"])
        if not table:
            return None,None,None,None,"unsupported_entity_type"
        entity=self.entities[table].get(row["EntityId"])
        if not entity:
            return table,None,None,None,"entity_id_not_in_declared_context"
        if table=="Lessons":
            key,binding,rule=self.lesson_course(row["EntityId"],row["UserId"])
        else:
            key=self.aliases.get((table,row["EntityId"]))
            binding,rule=None,"verified_catalog_alias" if key else "missing_catalog_alias"
        return table,entity,key,binding,rule

def related_materials(rows,materials,aliases):
    import json
    by_id=defaultdict(set)
    by_source={(a.source_table,a.source_record_id):a.material_key for a in aliases}
    owners={m.material_key:m for m in materials}
    for alias in aliases:
        by_id[alias.source_record_id].add(alias.material_key)
    result=[]
    for row in rows:
        full_key=json.dumps([row["Id"],row["ItemId"],row["ItemTypeId"]],separators=(",",":"))
        source=by_id.get(row["Id"],set())
        target=by_source.get((TARGET_TYPE_TABLES.get(row["ItemTypeId"]),row["ItemId"]))
        source_key=next(iter(source)) if len(source)==1 else None
        state="ambiguous" if len(source)>1 else "unresolved" if not source_key or not target else "resolved"
        if source_key and source_key==target:
            state="self_relation"
        flags=[]
        if source_key and not owners[source_key].is_discoverable: flags.append("source_not_discoverable")
        if target and not owners[target].is_discoverable: flags.append("target_not_discoverable")
        result.append(RelatedMaterial(relation_id=digest(["RecommendedItems",full_key]),source_record_id=full_key,
            source_material_key=source_key,target_material_key=target,status=state,
            resolution_rule="unique_source_membership_and_contextual_target",order=int(row["Order"]) if row["Order"] else None,
            raw_course_id=row["CourseId"] or None,quality_flags=flags))
    return sorted(result,key=lambda r:r.relation_id)
