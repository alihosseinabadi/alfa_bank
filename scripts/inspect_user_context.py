"""Public synthetic demo and private local inspection of a versioned RequestContext."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.ml.user_profile import build_user_profile
from app.ml.request_context import build_request_context
from app.ml.profile_contracts import ExplicitPreferences,ExplicitConstraints,UserProfile
from app.ml.profile_policy import default_policy,ProfilePolicy
from app.data_preparation.contracts import Material,SourceIdentity
from app.data_preparation.history_contracts import Observation,LearningState
from app.data_preparation.history_io import resolve_bundle,read_jsonl,load_catalog
from app.data_preparation.profile_bundle import verify_profiles

def demo_material(key,title,topics,item_type="course"):
    return Material(material_key=key,item_type=item_type,source_identities=[SourceIdentity(table="Synthetic",record_id=key)],
        title=title,topics=topics,url="https://example.invalid/"+key,access_type="Открытый",
        publication_status="Опубликовано",is_discoverable=True,snapshot_id="synthetic",extracted_at="synthetic")

def demo_observation(identity,key,kind="enrollment_state",rating=None):
    return Observation(observation_id=identity,source_table="UserRatings" if rating is not None else
        "CourseUserLessonBindings" if kind=="lesson_progress" else "CourseUserBindings",
        source_record_id=identity,source_snapshot_id="synthetic",user_key="organizer:demo",source_user_id="demo",
        observation_kind="explicit_rating" if rating is not None else kind,
        source_entity_table="Courses",source_entity_id=key,material_key=key,resolution_status="accepted",
        resolution_rule="synthetic_demo",ingestion_time="2026-01-01T12:00:00+00:00",
        event_time="2025-01",time_granularity="month",time_confidence="coarse",available_from_month="2025-01",
        evaluation_eligible=kind!="enrollment_state",raw_dates={"Completed":"2025-01-01 12:00:00+00"} if kind=="lesson_progress" else {},
        rating_value=rating,rating_group_id="96ee8fd2-fdb4-4a9a-bc10-3b2e7291c0d7" if rating is not None else None,
        rating_scale_status="resolved" if rating is not None else "not_applicable",
        rating_scale_values=[1,2,3,4,5] if rating is not None else [])

def run_demo():
    finance=demo_material("course:finance","Деньги бизнеса",["Финансы"])
    marketing=demo_material("course:marketing","Первые продажи",["Маркетинг"])
    calculator=demo_material("calculator:tool","Расчёт налога",[],item_type="calculator")
    cases=[
      ("new_user_with_task",[],"Как продвигать бизнес?",ExplicitPreferences(),ExplicitConstraints()),
      ("single_course",[demo_observation("e1",finance.material_key)],"",ExplicitPreferences(),ExplicitConstraints()),
      ("many_lessons_one_course",[demo_observation("p"+str(i),finance.material_key,"lesson_progress") for i in range(1000)]+[
          demo_observation("other",marketing.material_key,"lesson_progress")],"",ExplicitPreferences(),ExplicitConstraints()),
      ("negative_rating",[demo_observation("e2",finance.material_key),demo_observation("r1",finance.material_key,rating=1)],"",ExplicitPreferences(),ExplicitConstraints()),
      ("calculator_without_topics",[demo_observation("r2",calculator.material_key,rating=5)],"",ExplicitPreferences(),ExplicitConstraints()),
      ("unknown_user_no_task",[],"",ExplicitPreferences(),ExplicitConstraints()),
      ("task_switch",[demo_observation("e3",finance.material_key)],"Нужен шаблон для маркетинга",ExplicitPreferences(),ExplicitConstraints(formats=["document"],available_time_minutes=10)),
      ("optional_onboarding",[],"",ExplicitPreferences(business_stage="starting",industry="retail",selected_topics=["Продажи"],formats=["article"]),ExplicitConstraints()),
    ]
    result=[]
    for label,items,task,prefs,constraints in cases:
        profile=build_user_profile("organizer:demo",items,[finance,marketing,calculator],prefs)
        context=build_request_context(profile,task,constraints)
        result.append({"scenario":label,"synthetic":True,"support_material_count":profile.support_material_count,
            "topic_weights":profile.topic_weights,"avoidance_weights":profile.avoidance_weights,
            "query":context.query_text,"query_source":context.query_source,"history_weight":context.history_weight,
            "formats":context.formats,"available_time_minutes":context.available_time_minutes,
            "cold_start":context.cold_start,"fallback_required":context.fallback_required,"clarification":context.clarification,
            "profile_version":profile.profile_version})
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--demo",action="store_true",help="Public synthetic cases; no organizer records are printed")
    parser.add_argument("--user-key")
    parser.add_argument("--task",default="")
    parser.add_argument("--formats",nargs="*",choices=["course","article","document","webinar","podcast","glossary","calculator"])
    parser.add_argument("--time-minutes",type=int)
    parser.add_argument("--profiles-dir",type=Path,default=ROOT/"data/processed/profiles")
    parser.add_argument("--history-dir",type=Path,default=ROOT/"data/processed/history")
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--source-dir",type=Path,default=ROOT/"data/interim/history")
    parser.add_argument("--private",action="store_true",help="Print private context identifiers locally; never publish this output")
    args=parser.parse_args()
    if args.demo:
        print(json.dumps(run_demo(),ensure_ascii=False,indent=2));return
    if not args.user_key:parser.error("Use --demo or --user-key")
    manifest,_=verify_profiles(args.profiles_dir,args.history_dir,args.catalog_dir,args.source_dir)
    profiles=read_jsonl(resolve_bundle(args.profiles_dir)/"profiles.jsonl",UserProfile)
    profile=next((p for p in profiles if p.user_key==args.user_key),None)
    if profile is None:
        materials,_,_,catalog=load_catalog(args.catalog_dir)
        profile=build_user_profile(args.user_key,[],materials,history_bundle_id=manifest["history_bundle_id"],
            catalog_bundle_id=catalog["bundle_id"],cutoff_month=manifest["config"]["cutoff_month"],policy=ProfilePolicy.model_validate(manifest["config"]["policy"]))
    states=read_jsonl(resolve_bundle(args.history_dir)/"learning_state.jsonl",LearningState) if profile.mode=="current" else []
    context=build_request_context(profile,args.task,ExplicitConstraints(formats=args.formats,available_time_minutes=args.time_minutes),states)
    payload=context.model_dump()
    if not args.private:
        payload["user_key"]="[redacted]"
        payload["continuation_candidates"]=[{"requires_access_check":True,"requires_progression_check":True,
            "candidate_count":len(c.candidate_lesson_ids)} for c in context.continuation_candidates]
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
