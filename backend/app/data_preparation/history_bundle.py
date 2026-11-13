"""Small orchestration layer for validated stage-3 history artifacts."""
import json
from pathlib import Path
import subprocess
from .chunking import digest
from .history_io import load_source,load_catalog,publish_bundle,file_hash,resolve_bundle,verify_files,read_jsonl
from .user_history import normalize_history,validate_tables,validate_catalog_support
from .history_audit import audit_history
from .history_contracts import HISTORY_VERSION,TIME_POLICY,RESOLUTION_VERSION,Observation,LearningState,RelatedMaterial
from .history_time import before_cutoff

OUTPUT_MODELS={name:Observation for name in ("observations","profile_inputs","evaluation_inputs",
                "unassigned_observations","rejected_observations")}
OUTPUT_MODELS.update(learning_state=LearningState,related_materials=RelatedMaterial)

def build_history(source_dir:Path,catalog_dir:Path,output_dir:Path,root:Path,cutoff_month:str|None=None):
    tables,source=load_source(source_dir)
    materials,aliases,links,catalog=load_catalog(catalog_dir)
    data=normalize_history(tables,source,materials,aliases,links)
    audit=audit_history(data,tables,source,catalog,materials,aliases,links)
    outputs={name+".jsonl":data[name] for name in OUTPUT_MODELS}
    if cutoff_month:
        # One boundary for all users; tied months stay together.
        outputs["evaluation_before_cutoff.jsonl"]=[o for o in data["evaluation_inputs"] if before_cutoff(o,cutoff_month)]
        outputs["evaluation_from_cutoff.jsonl"]=[o for o in data["evaluation_inputs"] if not before_cutoff(o,cutoff_month)]
    outputs["audit.json"]=audit
    config={"history_version":HISTORY_VERSION,"time_policy":TIME_POLICY,"resolution_version":RESOLUTION_VERSION,
            "cutoff_month":cutoff_month,"user_namespace":"organizer","runtime_access_required":True}
    code_files=list((root/"backend/app/data_preparation").glob("*.py"))+[
        root/"scripts/export_user_history.py",root/"scripts/build_user_history.py",root/"scripts/verify_user_history.py"]
    code_hashes={str(p.relative_to(root)):file_hash(p) for p in sorted(code_files)}
    bundle_id=digest({"source":source["snapshot_id"],"catalog":catalog["bundle_id"],"config":config,
                      "code_sha256":code_hashes,"outputs":{name:digest([x.model_dump() if hasattr(x,"model_dump") else x for x in value])
                      if isinstance(value,list) else digest(value) for name,value in outputs.items()}})
    commit=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    dirty=bool(subprocess.check_output(["git","-C",str(root),"status","--porcelain"],text=True).strip())
    metadata={"config":config,"source_snapshot":source["snapshot_id"],"catalog_bundle_id":catalog["bundle_id"],
              "source_extracted_at":source["extracted_at"],"code_commit":commit,"working_tree_dirty":dirty,
              "code_sha256":code_hashes}
    return publish_bundle(output_dir,bundle_id,outputs,metadata),audit

def verify_history(history_dir:Path,source_dir:Path,catalog_dir:Path):
    bundle=resolve_bundle(history_dir)
    manifest=json.loads((bundle/"manifest.json").read_text())
    if manifest["config"]["history_version"]!=HISTORY_VERSION:
        raise ValueError("Incompatible history version")
    verify_files(bundle,manifest)
    tables,source=load_source(source_dir)
    materials,aliases,links,catalog=load_catalog(catalog_dir)
    if manifest["source_snapshot"]!=source["snapshot_id"] or manifest["catalog_bundle_id"]!=catalog["bundle_id"]:
        raise ValueError("Incompatible pinned source/catalog bundle")
    validate_tables(tables); validate_catalog_support(tables,materials,aliases,links)
    data={name:read_jsonl(bundle/(name+".jsonl"),model) for name,model in OUTPUT_MODELS.items()}
    stored_audit=json.loads((bundle/"audit.json").read_text())
    data["supporting_audit"]=stored_audit["supporting"]
    audit=audit_history(data,tables,source,catalog,materials,aliases,links)
    if audit!=stored_audit:
        raise ValueError("Stored history audit mismatch")
    cutoff=manifest["config"]["cutoff_month"]
    if cutoff:
        before=read_jsonl(bundle/"evaluation_before_cutoff.jsonl",Observation)
        after=read_jsonl(bundle/"evaluation_from_cutoff.jsonl",Observation)
        expected=data["evaluation_inputs"]
        if [o.observation_id for o in before]!=[o.observation_id for o in expected if before_cutoff(o,cutoff)] or [
            o.observation_id for o in after]!=[o.observation_id for o in expected if not before_cutoff(o,cutoff)]:
            raise ValueError("Invalid temporal partition")
    return manifest,audit
