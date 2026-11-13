"""File adapter for MVP profiles; algorithms remain in app.ml."""
from collections import Counter,defaultdict
import json
from pathlib import Path
import subprocess
from .history_io import resolve_bundle,load_source,load_catalog,read_jsonl,file_hash,verify_files,publish_bundle
from .history_bundle import verify_history
from .history_contracts import Observation,LearningState
from .history_time import before_cutoff
from app.ml.profile_contracts import UserProfile,ExplicitPreferences,PROFILE_SCHEMA_VERSION
from app.ml.profile_policy import ProfilePolicy,default_policy,fingerprint
from app.ml.user_profile import build_user_profile

def load_profile_inputs(history_dir,catalog_dir,source_dir):
    history_path=resolve_bundle(history_dir)
    history,audit=verify_history(history_dir,source_dir,catalog_dir)
    materials,_,_,catalog=load_catalog(catalog_dir)
    tables,source=load_source(source_dir)
    return history_path,history,catalog,materials,tables,source

def validate_policy_scales(policy,tables):
    active_groups={r["Id"] for r in tables["RatingGroups"] if r["IsDeleted"]=="f"}
    values=defaultdict(set)
    for row in tables["Ratings"]:
        if row["IsDeleted"]=="f" and row["RatingGroupId"] in active_groups:
            values[row["RatingGroupId"]].add(int(row["Value"]))
    group_questions={r["Id"]:(r["Question"] or "").strip() for r in tables["RatingGroups"]}
    value_questions={(r["RatingGroupId"],int(r["Value"])):(r["Question"] or "").strip() for r in tables["Ratings"] if r["IsDeleted"]=="f"}
    for identity,rule in policy.rating_rules.items():
        if identity not in active_groups or sorted(values[identity])!=sorted(set(rule.scale_values)):
            raise ValueError("Reviewed rating dictionary no longer matches policy")
        if rule.reviewed_group_question is None or rule.reviewed_group_question.strip()!=group_questions[identity] or set(rule.reviewed_value_questions)!=values[identity] or any(rule.reviewed_value_questions[v].strip()!=value_questions[(identity,v)] for v in values[identity]):
            raise ValueError("Reviewed rating question semantics changed or were not reviewed")

def prepare_profiles(history_path,history,catalog,materials,policy,explicit,cutoff_month=None):
    import re
    if cutoff_month is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",cutoff_month):
        raise ValueError("cutoff_month must be YYYY-MM")
    filename="evaluation_inputs.jsonl" if cutoff_month else "profile_inputs.jsonl"
    observations=read_jsonl(history_path/filename,Observation)
    if cutoff_month:
        observations=[o for o in observations if before_cutoff(o,cutoff_month)]
        users={o.user_key for o in observations}
    else:
        users={o.user_key for o in read_jsonl(history_path/"observations.jsonl",Observation)}
    users.update(explicit)
    grouped=defaultdict(list)
    for o in observations:grouped[o.user_key].append(o)
    return [build_user_profile(user,grouped[user],materials,explicit.get(user),policy,
            history_bundle_id=history["bundle_id"],catalog_bundle_id=catalog["bundle_id"],
            cutoff_month=cutoff_month) for user in sorted(users)]

def audit_profiles(profiles,materials,history,catalog,policy):
    owners={m.material_key:m for m in materials}
    checks={
        "unique_users":len({p.user_key for p in profiles})==len(profiles),
        "unique_profile_versions":len({p.profile_version for p in profiles})==len(profiles),
        "compatible_versions":all(p.schema_version==PROFILE_SCHEMA_VERSION and p.policy_hash==policy.identity() and
            p.history_bundle_id==history["bundle_id"] and p.catalog_bundle_id==catalog["bundle_id"] for p in profiles),
        "normalized_topic_weights":all(not p.topic_weights or abs(sum(p.topic_weights.values())-1)<1e-9 for p in profiles),
        "normalized_avoidance_weights":all(not p.avoidance_weights or abs(sum(p.avoidance_weights.values())-1)<1e-9 for p in profiles),
        "bounded_weights":all(0<=v<=1 for p in profiles for v in list(p.topic_weights.values())+list(p.avoidance_weights.values())),
        "one_evidence_per_material":all(len({e.material_key for e in p.material_evidence})==len(p.material_evidence) for p in profiles),
        "material_evidence_resolves":all(e.material_key in owners for p in profiles for e in p.material_evidence),
        "bounded_material_contribution":all(0<=e.net_strength<=1 and e.net_strength==max(e.positive_strength-e.negative_strength,0.0)
            for p in profiles for e in p.material_evidence),
        "support_is_distinct_materials":all(e.support_count==len(set(e.supporting_material_keys)|set(e.negative_material_keys))
            for p in profiles for e in p.topic_evidence),
        "confidence_is_bounded_heuristic":all(not p.confidence_is_calibrated and all(
            0<=e.confidence<=e.support_count/(e.support_count+policy.confidence_prior_materials)+1e-12 for e in p.topic_evidence) for p in profiles),
        "no_inferred_format_preferences":all("observed_formats_are_not_preferences" in p.quality_flags for p in profiles),
        "historical_learning_state_excluded":all(p.learning_state_reference is None for p in profiles if p.mode=="historical"),
    }
    report={"passed":all(checks.values()),"checks":checks,"profiles":len(profiles),
        "profiles_with_topics":sum(bool(p.topic_weights) for p in profiles),
        "profiles_with_title_fallbacks":sum(bool(p.title_fallbacks) for p in profiles),
        "profiles_with_negative_evidence":sum(bool(p.avoidance_weights) for p in profiles),
        "cold_start_profiles":sum(p.cold_start for p in profiles),
        "cold_start_reasons":dict(Counter(p.cold_start_reason for p in profiles if p.cold_start)),
        "material_support_distribution":{str(k):v for k,v in sorted(Counter(p.support_material_count for p in profiles).items())},
        "skipped_observations":dict(Counter({key:sum(p.skipped_observations.get(key,0) for p in profiles)
            for key in set(k for p in profiles for k in p.skipped_observations)})),
        "max_material_net_strength":max((e.net_strength for p in profiles for e in p.material_evidence),default=0),
        "history_bundle_id":history["bundle_id"],"catalog_bundle_id":catalog["bundle_id"],
        "limitations":["Profile strengths and confidence are transparent hypotheses, not calibrated preferences.",
            "Current task is kept separate and wins over history.",
            "Observed formats reflect collection bias, not a learned format preference.",
            "This stage does not retrieve or rank materials or demonstrate conversion lift."]}
    if not report["passed"]:raise ValueError("Profile acceptance failed: "+str([k for k,v in checks.items() if not v]))
    return report

def build_profiles(history_dir,catalog_dir,source_dir,output_dir,root,*,cutoff_month=None,policy=None,explicit=None):
    policy=policy or default_policy(); explicit=explicit or {}
    path,history,catalog,materials,tables,source=load_profile_inputs(history_dir,catalog_dir,source_dir)
    validate_policy_scales(policy,tables)
    profiles=prepare_profiles(path,history,catalog,materials,policy,explicit,cutoff_month)
    audit=audit_profiles(profiles,materials,history,catalog,policy)
    config={"schema_version":PROFILE_SCHEMA_VERSION,"mode":"historical" if cutoff_month else "current",
            "cutoff_month":cutoff_month,"policy":policy.model_dump(),
            "explicit_preferences":{key:value.model_dump() for key,value in sorted(explicit.items())}}
    paths=list((root/"backend/app/ml").glob("*.py"))+[root/"backend/app/data_preparation/profile_bundle.py",
        root/"scripts/build_user_profiles.py",root/"scripts/verify_user_profiles.py",root/"scripts/inspect_user_context.py"]
    code_hashes={str(p.relative_to(root)):file_hash(p) for p in sorted(paths)}
    identity=fingerprint({"history":history["bundle_id"],"catalog":catalog["bundle_id"],"config":config,"code":code_hashes,
                          "profiles":[p.profile_version for p in profiles]})
    metadata={"config":config,"history_bundle_id":history["bundle_id"],"catalog_bundle_id":catalog["bundle_id"],
        "history_source_snapshot":source["snapshot_id"],
        "reviewed_rating_dictionary_hashes":{name:source["files"][name]["sha256"] for name in ("Ratings","RatingGroups")},
        "working_tree_dirty":bool(subprocess.check_output(["git","-C",str(root),"status","--porcelain"],text=True).strip()),
        "code_sha256":code_hashes,"code_commit":subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()}
    output=publish_bundle(output_dir,identity,{"profiles.jsonl":profiles,"audit.json":audit},metadata)
    return output,audit

def verify_profiles(profiles_dir,history_dir,catalog_dir,source_dir):
    bundle=resolve_bundle(profiles_dir)
    manifest=json.loads((bundle/"manifest.json").read_text())
    if manifest["config"]["schema_version"]!=PROFILE_SCHEMA_VERSION:raise ValueError("Incompatible profile schema")
    verify_files(bundle,manifest)
    path,history,catalog,materials,tables,source=load_profile_inputs(history_dir,catalog_dir,source_dir)
    if manifest["history_bundle_id"]!=history["bundle_id"] or manifest["catalog_bundle_id"]!=catalog["bundle_id"]:
        raise ValueError("Incompatible profile/history/catalog bundle")
    if manifest["history_source_snapshot"]!=source["snapshot_id"] or manifest["reviewed_rating_dictionary_hashes"]!={name:source["files"][name]["sha256"] for name in ("Ratings","RatingGroups")}:
        raise ValueError("Profile rating review provenance mismatch")
    policy=ProfilePolicy.model_validate(manifest["config"]["policy"])
    validate_policy_scales(policy,tables)
    explicit={key:ExplicitPreferences.model_validate(value) for key,value in manifest["config"]["explicit_preferences"].items()}
    profiles=read_jsonl(bundle/"profiles.jsonl",UserProfile)
    expected=prepare_profiles(path,history,catalog,materials,policy,explicit,manifest["config"]["cutoff_month"])
    if [p.model_dump() for p in profiles]!=[p.model_dump() for p in expected]:
        raise ValueError("Profile/source reconstruction mismatch")
    audit=audit_profiles(profiles,materials,history,catalog,policy)
    if audit!=json.loads((bundle/"audit.json").read_text()):raise ValueError("Profile audit mismatch")
    return manifest,audit
