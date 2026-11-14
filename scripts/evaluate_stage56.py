"""Frozen, blinded quality audit of lexical retrieval and the stage-6 prior.

Only aggregate output is suitable for Git. Organizer cards/judgments stay local.
"""
import argparse
import json
import platform
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data_preparation.history_contracts import Observation
from app.data_preparation.history_io import read_jsonl, write_json, file_hash, verify_files
from app.data_preparation.ranking_bundle import load_ranking_catalog
from app.ml.user_profile import build_user_profile
from app.ml.request_context import build_request_context
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences
from app.ml.profile_policy import fingerprint
from app.ml.prior_ranking import PriorPolicy, rank_candidates
from app.ml.ranking_inputs import from_search_result, from_channel
from app.ml.feature_registry import REGISTRY_HASH, validate_features
from app.ml.retrieval_baselines import topic_baseline
from app.ml.retrieval_metrics import judged_metrics
from app.ml.tfidf_retriever import eligible_for_context
from app.ml.bm25_retriever import BM25Retriever

METHODS = ("topic", "tfidf", "bm25", "tfidf_prior", "bm25_prior")

def evaluation_context(case, materials, catalog_id):
    prefs = ExplicitPreferences(selected_topics=case.get("selected_topics", []),
        industry=case.get("industry"))
    observations = []
    for i, topic in enumerate(case.get("history_topics", [])):
        owners = [m for m in materials if m.item_type == "course" and m.is_discoverable and topic in m.topics]
        if not owners:
            raise ValueError("Synthetic history needs a real course with topic: " + topic)
        owner = min(owners, key=lambda m: (len(m.topics), m.material_key))
        observations.append(Observation(observation_id="synthetic:"+str(i), source_table="CourseUserBindings",
            source_record_id="synthetic:"+str(i), source_snapshot_id="synthetic-quality-v1",
            user_key="organizer:synthetic-quality", source_user_id="synthetic-quality",
            observation_kind="enrollment_state", source_entity_table="Courses",
            source_entity_id=owner.material_key.split(":", 1)[1], material_key=owner.material_key,
            resolution_status="accepted", resolution_rule="synthetic_scenario_not_actual_user",
            ingestion_time="2026-11-14T12:00:00+03:00"))
    profile = build_user_profile("organizer:synthetic-quality", observations, materials, prefs,
        history_bundle_id="synthetic-quality-v1", catalog_bundle_id=catalog_id)
    constraints = ExplicitConstraints(formats=case.get("formats", []),
        available_time_minutes=case.get("available_time_minutes"),
        budget_preference=case.get("budget_preference"))
    return profile, build_request_context(profile, case.get("task", ""), constraints)

def current_code_hashes():
    paths = list((ROOT / "backend/app/ml").glob("*.py"))
    paths += [Path(__file__), ROOT / "backend/app/data_preparation/ranking_bundle.py",
              ROOT / "backend/app/data_preparation/retrieval_bundle.py"]
    return {str(p.relative_to(ROOT)): file_hash(p) for p in sorted(paths)}

def run_methods(index, lexical, materials, manifest, profile, context, policy):
    lookup = {r.chunk_id:r for r in index.rows}
    provenance = dict(index_bundle_id=manifest["bundle_id"], catalog_bundle_id=manifest["catalog_bundle_id"],
                      retrieval_policy_id=fingerprint({"tfidf":index.policy.model_dump(), "bm25":[lexical.k1, lexical.b, lexical.min_query_coverage]}))
    outputs = {}
    batches = {}
    times = {}
    for name, run in (("topic", lambda:topic_baseline(index,context,50)), ("tfidf", lambda:index.query(context,50))):
        start = time.perf_counter(); result = run(); times[name] = (time.perf_counter()-start)*1000
        batch = from_search_result(result,lookup,context,**provenance)
        batches[name] = batch
        outputs[name] = {"keys":[h.material_key for h in batch.hits], "status":result.status,
            "clarification":result.clarification, "evidence":{h.material_key:[e.chunk.chunk_id for e in h.evidence] for h in batch.hits}}
    start=time.perf_counter(); result=lexical.query(context,50);times["bm25"]=(time.perf_counter()-start)*1000
    batch=from_channel(result,context,method="bm25",**provenance);batches["bm25"]=batch
    outputs["bm25"]={"keys":[h.material_key for h in batch.hits],"status":batch.status,
        "clarification":batch.clarification,"evidence":{h.material_key:[e.chunk.chunk_id for e in h.evidence] for h in batch.hits}}
    ranked_results = {}
    for base in ("tfidf","bm25"):
        start=time.perf_counter()
        ranked=rank_candidates(batches[base],materials,context,profile=profile,policy=policy,k=50)
        elapsed=(time.perf_counter()-start)*1000
        ranked_results[base]=ranked
        outputs[base+"_prior"]={"keys":[c.material_key for c in ranked.candidates],"status":ranked.status,
            "clarification":ranked.clarification,"evidence":{c.material_key:[e.chunk_id for e in c.citations] for c in ranked.candidates},
            "rerank_ms":elapsed,"components":{c.material_key:c.score_components for c in ranked.candidates}}
        times[base+"_prior"]=times[base]+elapsed
    for name,output in outputs.items():
        keys=output["keys"]
        checks={"unique":len(keys)==len(set(keys)), "cap50":len(keys)<=50,
            "eligibility":all(eligible_for_context(index.materials[k],context) for k in keys)}
        for key,identities in output["evidence"].items():
            checks["public_scope"] = checks.get("public_scope",True) and all(
                lookup[i].access_scope=="public" and lookup[i].material_key==key and
                (index.materials[key].access_type=="Открытый" or lookup[i].content_kind=="metadata") for i in identities)
        output["checks"]=checks
        output["latency_ms"]=times[name]
    for base,ranked in ranked_results.items():
        for card in ranked.candidates:
            validate_features(card.features)
            if abs(sum(card.score_components.values())-card.prior_score)>1e-12:
                raise ValueError("Inconsistent prior score")
            for citation in card.citations:
                chunk=lookup[citation.chunk_id]
                if citation.excerpt not in chunk.text or citation.source_block_ids!=chunk.source_block_ids:
                    raise ValueError("Invalid public citation")
            for reason in card.reasons:
                if card.features.values[reason.feature]!=reason.value:
                    raise ValueError("Unsupported ranking reason")
    return outputs

def collect(args):
    if (args.eval_dir/"collection_manifest.json").exists():
        raise FileExistsError("Frozen collection exists; create a new version")
    cases=json.loads(args.base_cases.read_text())+json.loads(args.extra_cases.read_text())
    if len({c["case_id"] for c in cases})!=len(cases):
        raise ValueError("Duplicate case identity")
    seeds=json.loads(args.seed_labels.read_text())
    index,manifest,materials=load_ranking_catalog(args.index_dir,args.catalog_dir)
    lexical=BM25Retriever().fit(list(index.materials.values()),index.rows)
    policy=PriorPolicy()
    freeze={"index_bundle_id":manifest["bundle_id"],"catalog_bundle_id":manifest["catalog_bundle_id"],
        "prior_policy":policy.model_dump(),"prior_policy_id":policy.identity(),"feature_registry_hash":REGISTRY_HASH,
        "tfidf_policy":index.policy.model_dump(),"bm25_parameters":[lexical.k1,lexical.b,lexical.min_query_coverage],
        "code_sha256":current_code_hashes(),"base_cases_sha256":file_hash(args.base_cases),
        "extra_cases_sha256":file_hash(args.extra_cases),"seed_labels_sha256":file_hash(args.seed_labels),
        "profile_construction":"Artificial enrollments on real catalog courses; actual build_user_profile; no real users.",
        "assessment":"Parameters fixed before results. Old cases are diagnostic; new cases are independent-agent holdout.",
        "unavailable_methods":["e5","hybrid"],"runtime":{"python":platform.python_version(),"platform":platform.platform()}}
    rows=[];pool=[];latencies=defaultdict(list);owners={m.material_key:m for m in materials};by_id={r.chunk_id:r for r in index.rows}
    for case in cases:
        profile,context=evaluation_context(case,materials,manifest["catalog_bundle_id"])
        methods=run_methods(index,lexical,materials,manifest,profile,context,policy)
        rows.append({"case":case,"query_text":context.query_text,"query_source":context.query_source,
                     "derived_topic_weights":profile.topic_weights,"methods":methods})
        if not case.get("behavior"):
            keys={k for method in methods.values() for k in method["keys"][:10]}
            keys.update(s["material_key"] for s in seeds if s["case_id"]==case["case_id"])
            cards=[]
            for key in sorted(keys):
                evidence={index._metadata_row(key).chunk_id}
                evidence.update(identity for method in methods.values() for identity in method["evidence"].get(key,[]))
                material=owners[key]
                cards.append({"material_key":key,"title":material.title,"item_type":material.item_type,
                    "topics":material.topics,"industry_labels":material.industry_labels,"access_type":material.access_type,
                    "duration_minutes":material.duration_minutes,"listed_price":material.listed_price,"url_state":material.url_state,
                    "public_evidence":[by_id[identity].text for identity in sorted(evidence)]})
            pool.append({"case":case,"query_text":context.query_text,"derived_topic_weights":profile.topic_weights,"cards":cards})
        # Repeat warm measurements on every case; no data or weights are changed.
        for _ in range(3):
            measured=run_methods(index,lexical,materials,manifest,profile,context,policy)
            for name,method in measured.items():latencies[name].append(method["latency_ms"])
    latency={name:{"queries":len(values),"p50_ms":float(np.percentile(values,50)),"p95_ms":float(np.percentile(values,95))}
             for name,values in latencies.items()}
    args.eval_dir.mkdir(parents=True,exist_ok=True)
    for name,data in (("cases.json",cases),("seed_judgments.json",seeds),("freeze.json",freeze),
                      ("rankings.json",rows),("blind_pool.json",pool),("latency.json",latency)):
        write_json(args.eval_dir/name,data)
    files={name:file_hash(args.eval_dir/name) for name in ("cases.json","seed_judgments.json","freeze.json","rankings.json","blind_pool.json","latency.json")}
    write_json(args.eval_dir/"collection_manifest.json",{"files":files,"collection_id":fingerprint(files)})
    print(json.dumps({"cases":len(cases),"relevance_cases":len(pool),"blind_pairs":sum(len(p["cards"]) for p in pool),
                      "collection_id":fingerprint(files)},indent=2))

def paired_delta(values,seed=781):
    values=np.asarray(values,dtype=float)
    rng=np.random.default_rng(seed)
    samples=values[rng.integers(0,len(values),size=(10000,len(values)))].mean(axis=1)
    return {"mean_delta":float(values.mean()),"bootstrap95":[float(np.percentile(samples,2.5)),float(np.percentile(samples,97.5))],
            "cases":len(values),"note":"Exploratory paired bootstrap; catalog-aware scenarios are not traffic."}

def score(args):
    root=args.eval_dir
    collection=json.loads((root/"collection_manifest.json").read_text());verify_files(root,collection)
    freeze=json.loads((root/"freeze.json").read_text())
    if freeze["prior_policy"]!=PriorPolicy().model_dump() or freeze["code_sha256"]!=current_code_hashes():
        raise ValueError("Frozen scoring/model code changed; retain old collection and make a new version")
    pool=json.loads((root/"blind_pool.json").read_text())
    rows=json.loads((root/"rankings.json").read_text())
    labels=json.loads((root/"pool_judgments.json").read_text())
    expected={(p["case"]["case_id"],c["material_key"]) for p in pool for c in p["cards"]}
    found={}
    for label in labels:
        identity=(label["case_id"],label["material_key"])
        if identity not in expected or type(label["grade"]) is not int or label["grade"] not in (0,1,2,3):
            raise ValueError("Invalid blind-pool judgment")
        if identity in found:raise ValueError("Duplicate judgment")
        found[identity]=label["grade"]
    if set(found)!=expected:
        raise ValueError("Incomplete blind pool: "+str(len(expected-set(found))))
    seeds=json.loads((root/"seed_judgments.json").read_text())
    if any(found.get((s["case_id"],s["material_key"]))!=s["grade"] for s in seeds):
        raise ValueError("Frozen seed labels were changed")
    judgments=defaultdict(dict)
    for (case,key),grade in found.items():judgments[case][key]=grade
    per_case=[]
    for row in rows:
        case=row["case"];identity=case["case_id"]
        for name,method in row["methods"].items():
            entry={"case_id":identity,"split":case["split"],"method":name,"behavior":case.get("behavior"),
                "returned":len(method["keys"]),"status":method["status"],"checks":method["checks"]}
            if case.get("behavior"):
                entry["behavior_passed"]=not method["keys"] and bool(method["clarification"])
                entry["specific_status_passed"]=case["behavior"]!="no_eligible" or method["status"]=="no_eligible"
            else:
                entry.update(judged_metrics(method["keys"],judgments[identity]))
                entry["positives_in_pool"]=sum(g>=2 for g in judgments[identity].values())
                entry["grades_top10"]=[judgments[identity][key] for key in method["keys"][:10]]
            per_case.append(entry)
    summary={}
    for split in ("dev","test","holdout","all"):
        summary[split]={}
        for name in METHODS:
            subset=[r for r in per_case if r["method"]==name and (split=="all" or r["split"]==split)]
            relevant=[r for r in subset if not r["behavior"]];behavior=[r for r in subset if r["behavior"]]
            summary[split][name]={"relevance_cases":len(relevant),
                **{metric:statistics.mean(r[metric] for r in relevant) if relevant else None
                   for metric in ("ndcg10","success5","pooled_recall50")},
                "behavior_passed":sum(r["behavior_passed"] for r in behavior),"behavior_cases":len(behavior),
                "specific_status_passed":sum(r["specific_status_passed"] for r in behavior),
                "all_constraints_passed":all(all(r["checks"].values()) for r in subset),
                "relevance_empty_rate":sum(r["returned"]==0 for r in relevant)/len(relevant) if relevant else None}
    deltas={};changes={}
    for base in ("tfidf","bm25"):
        for split in ("test","holdout","all"):
            chosen=[row for row in rows if not row["case"].get("behavior") and (split=="all" or row["case"]["split"]==split)]
            by_case={(r["case_id"],r["method"]):r for r in per_case}
            values=[by_case[(r["case"]["case_id"],base+"_prior")]["ndcg10"]-by_case[(r["case"]["case_id"],base)]["ndcg10"] for r in chosen]
            if values:deltas[base+"_"+split]=paired_delta(values)
        changes[base]=[row["case"]["case_id"] for row in rows
            if row["methods"][base]["keys"][:10]!=row["methods"][base+"_prior"]["keys"][:10]]
    report={"collection_id":collection["collection_id"],"freeze":freeze,"summary":summary,"per_case":per_case,
        "paired_ndcg_deltas":deltas,"changed_top10_cases":changes,"manual_judgments":len(labels),
        "labels_sha256":file_hash(root/"pool_judgments.json"),"latency":json.loads((root/"latency.json").read_text()),
        "limitations":["One independent agent reviewer; no organizer expert or inter-rater agreement.",
            "Old dev/test cases were previously inspected. Only additional holdout authored before outputs.",
            "Scenario histories are artificial enrollments over real courses, not relevance labels from real users.",
            "Judged pool is top10 union plus prior frozen seeds, not exhaustive catalog recall.",
            "E5 and hybrid artifacts absent; their earlier reported metrics are not reproduced.",
            "No purchase prediction, business lift or online A/B result."]}
    output=ROOT/"reports/quality_stage56.json"
    write_json(output,report)
    print(json.dumps({key:report[key] for key in ("summary","paired_ndcg_deltas","changed_top10_cases","manual_judgments","latency")},ensure_ascii=False,indent=2))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["collect","score"])
    p.add_argument("--eval-dir",type=Path,default=ROOT/"data/interim/quality_stage56")
    p.add_argument("--base-cases",type=Path,default=ROOT/"data/interim/retrieval_eval/cases.json")
    p.add_argument("--extra-cases",type=Path,default=ROOT/"data/interim/quality_stage56/new_cases.json")
    p.add_argument("--seed-labels",type=Path,default=ROOT/"data/interim/retrieval_eval/seed_judgments.json")
    p.add_argument("--index-dir",type=Path,default=ROOT/"artifacts/retrieval")
    p.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    args=p.parse_args()
    (collect if args.action=="collect" else score)(args)
if __name__=="__main__":main()
