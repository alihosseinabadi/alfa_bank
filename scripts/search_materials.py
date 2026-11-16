"""Local search demo: six cards by default; optional private profile context."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.ml.profile_contracts import ExplicitPreferences,ExplicitConstraints,UserProfile
from app.ml.user_profile import build_user_profile
from app.ml.request_context import build_request_context
from app.ml.retrieval_baselines import topic_baseline
from app.data_preparation.history_io import resolve_bundle,load_catalog,read_jsonl,verify_files
from app.data_preparation.history_contracts import LearningState
from app.data_preparation.retrieval_bundle import load_index

def context_for_case(case):
    prefs=ExplicitPreferences(selected_topics=case.get("selected_topics",[]))
    profile=build_user_profile("synthetic:retrieval-demo",[],[],prefs)
    # Synthetic history is an evaluation fixture, not organizer observations.
    if case.get("history_topics"):
        topics=case["history_topics"]
        profile=profile.model_copy(update={"topic_weights":{t:1/len(topics) for t in topics},
            "cold_start":False,"cold_start_reason":None})
    return build_request_context(profile,case.get("task",""),ExplicitConstraints(
        formats=case.get("formats",[]),available_time_minutes=case.get("available_time_minutes"),
        budget_preference=case.get("budget_preference")))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--task",default="")
    parser.add_argument("--formats",nargs="*",choices=["course","article","document","webinar","podcast","glossary","calculator"],default=[])
    parser.add_argument("--free-only",action="store_true")
    parser.add_argument("--time-minutes",type=int)
    parser.add_argument("--k",type=int,default=6)
    parser.add_argument("--baseline",action="store_true")
    parser.add_argument("--index-dir",type=Path,default=ROOT/"artifacts/retrieval")
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--profiles-dir",type=Path,default=ROOT/"data/processed/profiles")
    parser.add_argument("--history-dir",type=Path,default=ROOT/"data/processed/history")
    parser.add_argument("--user-key",help="Private local identifier; never logged in result")
    args=parser.parse_args()
    _,_,_,catalog=load_catalog(args.catalog_dir)
    index,manifest=load_index(args.index_dir,catalog_bundle_id=catalog["bundle_id"])
    if args.user_key:
        path=resolve_bundle(args.profiles_dir)
        profiles_manifest=json.loads((path/"manifest.json").read_text());verify_files(path,profiles_manifest)
        if profiles_manifest["catalog_bundle_id"]!=manifest["catalog_bundle_id"]:raise ValueError("Profile/catalog mismatch")
        profile=next((p for p in read_jsonl(path/"profiles.jsonl",UserProfile) if p.user_key==args.user_key),None)
        if profile is None:raise ValueError("User profile not found; use no --user-key for cold start")
        history_path=resolve_bundle(args.history_dir)
        history_manifest=json.loads((history_path/"manifest.json").read_text());verify_files(history_path,history_manifest)
        if profile.history_bundle_id!=history_manifest["bundle_id"]:raise ValueError("Profile/history mismatch")
        states=read_jsonl(history_path/"learning_state.jsonl",LearningState) if profile.mode=="current" else []
        context=build_request_context(profile,args.task,ExplicitConstraints(formats=args.formats,
            available_time_minutes=args.time_minutes,budget_preference="free_only" if args.free_only else None),states)
    else:
        context=context_for_case({"task":args.task,"formats":args.formats,"available_time_minutes":args.time_minutes,
            "budget_preference":"free_only" if args.free_only else None})
    result=(topic_baseline(index,context,args.k) if args.baseline else index.query(context,args.k)).model_dump()
    # The platform must resolve/check these private IDs, so demo exposes only count.
    result["continuation_candidates"]=[{"requires_access_check":True,"requires_progression_check":True,
        "candidate_count":len(c.candidate_lesson_ids)} for c in context.continuation_candidates]
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
