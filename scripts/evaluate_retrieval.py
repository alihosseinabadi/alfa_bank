"""Frozen synthetic tasks + independent local labels, never real user evaluation."""
import argparse,json,sys,time,statistics
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.retrieval_bundle import load_index
from app.data_preparation.history_io import file_hash,write_json
from app.ml.retrieval_baselines import topic_baseline
from app.ml.retrieval_metrics import judged_metrics
from app.ml.tfidf_retriever import eligible_for_context
from search_materials import context_for_case

def collect(index,cases):
    rows=[]
    for case in cases:
        context=context_for_case(case)
        methods={}
        for method,run in (("tfidf",index.query),("topic_baseline",lambda ctx,k:topic_baseline(index,ctx,k))):
            start=time.perf_counter();result=run(context,50);elapsed=(time.perf_counter()-start)*1000
            methods[method]={"result":result.model_dump(),"latency_ms":elapsed}
        rows.append({"case":case,"methods":methods})
    return rows

def blind_pool(index,rows,seeds):
    pool=[]
    for row in rows:
        case=row["case"]
        if case["behavior"]:continue
        keys={c["material_key"] for method in row["methods"].values() for c in method["result"]["candidates"][:10]}
        keys.update(label["material_key"] for label in seeds if label["case_id"]==case["case_id"])
        cards=[]
        for key in sorted(keys):
            material=index.materials[key]
            evidence={index._metadata_row(key).text}
            for method in row["methods"].values():
                for candidate in method["result"]["candidates"][:10]:
                    if candidate["material_key"]==key:
                        chunk=next(r for r in index.rows if r.chunk_id==candidate["evidence_chunk_id"])
                        evidence.add(chunk.text)
            cards.append({"material_key":key,"title":material.title,"item_type":material.item_type,
                "topics":material.topics,"tags":material.tags,"access_type":material.access_type,
                "duration_minutes":material.duration_minutes,"public_evidence":sorted(evidence)})
        pool.append({"case":case,"cards":cards})
    return pool

def evaluate(rows,labels,index):
    judgments=defaultdict(dict)
    for label in labels:
        case,key,grade=label["case_id"],label["material_key"],label["grade"]
        if grade not in (0,1,2,3):raise ValueError("Invalid manual grade")
        if key in judgments[case] and judgments[case][key]!=grade:raise ValueError("Conflicting frozen judgment")
        judgments[case][key]=grade
    per_case=[]
    for row in rows:
        case=row["case"];ctx=context_for_case(case)
        for method,run in row["methods"].items():
            result=run["result"];cards=result["candidates"];keys=[c["material_key"] for c in cards]
            checks={"unique":len(keys)==len(set(keys)),"cap":len(keys)<=50,
                "eligible":all(eligible_for_context(index.materials[c["material_key"]],ctx) for c in cards),
                "public_evidence":all(next(r for r in index.rows if r.chunk_id==c["evidence_chunk_id"]).access_scope=="public" for c in cards)}
            entry={"case_id":case["case_id"],"split":case["split"],"algorithm":method,
                "behavior":case["behavior"],"status":result["status"],"returned":len(cards),"checks":checks,"latency_ms":run["latency_ms"]}
            if case["behavior"]:
                entry["behavior_passed"]=not cards and bool(result["clarification"])
                if case["behavior"]=="no_eligible":entry["behavior_passed"] &= result["status"]=="no_eligible"
            else:entry.update(judged_metrics(keys,judgments[case["case_id"]]))
            per_case.append(entry)
    summary={}
    for split in ("dev","test"):
        summary[split]={}
        for method in ("tfidf","topic_baseline"):
            subset=[r for r in per_case if r["split"]==split and r["algorithm"]==method]
            relevant=[r for r in subset if not r["behavior"]];behavior=[r for r in subset if r["behavior"]]
            summary[split][method]={**{metric:statistics.mean(r[metric] for r in relevant) for metric in ("ndcg10","success5","pooled_recall50")},
                "relevance_cases":len(relevant),"behavior_passed":sum(r["behavior_passed"] for r in behavior),
                "behavior_cases":len(behavior),"all_constraints_passed":all(all(r["checks"].values()) for r in subset)}
    return {"summary":summary,"per_case":per_case,
        "limitations":["20 catalog-aware synthetic cases, not production traffic.",
            "16 relevance cases with independent agent judgments; not organizer expert labels.",
            "NDCG and recall use a pool of top10 of two methods plus frozen seed labels, not exhaustive catalog judgments.",
            "No conversion, causal lift, statistical significance or online A/B conclusion."]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--eval-dir",type=Path,default=ROOT/"data/interim/retrieval_eval")
    parser.add_argument("--index-dir",type=Path,default=ROOT/"artifacts/retrieval")
    parser.add_argument("--collect-only",action="store_true")
    args=parser.parse_args()
    index,manifest=load_index(args.index_dir)
    cases=json.loads((args.eval_dir/"cases.json").read_text())
    seeds=json.loads((args.eval_dir/"seed_judgments.json").read_text())
    rows=collect(index,cases)
    if args.collect_only:
        write_json(args.eval_dir/"rankings.json",rows)
        write_json(args.eval_dir/"blind_pool.json",blind_pool(index,rows,seeds))
        write_json(args.eval_dir/"config_freeze.json",{"bundle_id":manifest["bundle_id"],"policy":index.policy.model_dump(),
            "cases_sha256":file_hash(args.eval_dir/"cases.json"),"seeds_sha256":file_hash(args.eval_dir/"seed_judgments.json"),
            "note":"Parameters fixed a priori; no held-out metric tuning."})
        print(json.dumps({"collected_cases":len(rows),"blind_pool":str(args.eval_dir/"blind_pool.json")}))
        return
    freeze=json.loads((args.eval_dir/"config_freeze.json").read_text())
    if freeze["policy"]!=index.policy.model_dump() or freeze["cases_sha256"]!=file_hash(args.eval_dir/"cases.json") or freeze["seeds_sha256"]!=file_hash(args.eval_dir/"seed_judgments.json"):
        raise ValueError("Frozen evaluation changed")
    labels=seeds+json.loads((args.eval_dir/"pool_judgments.json").read_text())
    result=evaluate(rows,labels,index)
    # Warm query latency excludes disk loading, verification and fitting.
    times=[]
    for _ in range(5):
        for case in cases:
            ctx=context_for_case(case);start=time.perf_counter();index.query(ctx,50)
            times.append((time.perf_counter()-start)*1000)
    import numpy as np
    result["latency"]={"queries":len(times),"warm_p50_ms":float(np.percentile(times,50)),"warm_p95_ms":float(np.percentile(times,95))}
    result["provenance"]={"index_bundle_id":manifest["bundle_id"],"config_freeze_bundle_id":freeze["bundle_id"],
        "cases_sha256":file_hash(args.eval_dir/"cases.json"),"seed_labels_sha256":file_hash(args.eval_dir/"seed_judgments.json"),
        "pool_labels_sha256":file_hash(args.eval_dir/"pool_judgments.json"),"manual_labels":len({(x["case_id"],x["material_key"]) for x in labels})}
    (ROOT/"reports").mkdir(exist_ok=True)
    write_json(ROOT/"reports/retrieval_stage5_evaluation.json",result)
    print(json.dumps({"summary":result["summary"],"latency":result["latency"],"provenance":result["provenance"]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
