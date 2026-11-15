"""Additional diagnostics; does not change primary metrics, judgments or weights."""
import json,math,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.history_io import write_json,file_hash
from app.ml.profile_policy import fingerprint
from evaluate_stage56 import paired_delta

def useful_ndcg(keys,labels):
    def gain(grade):return 2**grade-1 if grade>=2 else 0
    def dcg(grades):return sum(gain(g)/math.log2(i+2) for i,g in enumerate(grades))
    ideal=dcg(sorted(labels.values(),reverse=True)[:10])
    return dcg([labels[k] for k in keys[:10]])/ideal if ideal else 0.0

def main():
    root=ROOT/"data/interim/quality_stage56"
    rows=json.loads((root/"rankings.json").read_text())
    judgments=json.loads((root/"pool_judgments.json").read_text())
    labels={}
    for item in judgments:labels.setdefault(item["case_id"],{})[item["material_key"]]=item["grade"]
    output={"definition":"Useful NDCG: gains of grades 0/1 are 0; grade2 gain3, grade3 gain7; no positive pool ->0.",
        "note":"Secondary diagnostic only; standard graded NDCG remains primary.",
        "scorer_sha256":file_hash(Path(__file__)),"primary_sha256":file_hash(ROOT/"reports/quality_stage56.json")}
    results=[];no_positive=[];active={}
    for row in rows:
        case=row["case"]
        if case.get("behavior"):continue
        identity=case["case_id"];grades=labels[identity]
        if not any(g>=2 for g in grades.values()):no_positive.append(identity)
        for name,method in row["methods"].items():
            keys=method["keys"]
            results.append({"case_id":identity,"split":case["split"],"method":name,
                "useful_ndcg10":useful_ndcg(keys,grades),
                "success1":float(bool(keys) and grades[keys[0]]>=2)})
            if name.endswith("_prior"):
                for feature in ("task_text_overlap","history_topic_match","avoidance_topic_match","industry_match","duration_fit"):
                    if any(abs(c[feature])>0 for c in method["components"].values()):
                        active.setdefault(name+":"+feature,[]).append(identity)
    summary={}
    for split in ("dev","test","holdout","all"):
        summary[split]={}
        for method in ("topic","tfidf","bm25","tfidf_prior","bm25_prior"):
            chosen=[r for r in results if r["method"]==method and (split=="all" or r["split"]==split)]
            summary[split][method]={key:statistics.mean(r[key] for r in chosen) for key in ("useful_ndcg10","success1")}
    changes={}
    for method in ("tfidf","bm25"):
        changes[method]={}
        for size in (1,5,10):
            changes[method]["top"+str(size)]=[r["case"]["case_id"] for r in rows
                if r["methods"][method]["keys"][:size]!=r["methods"][method+"_prior"]["keys"][:size]]
    output.update(summary=summary,no_useful_positive_in_pool=no_positive,active_components=active,
                  ranking_changes=changes,per_case=results)
    write_json(ROOT/"reports/quality_stage56_diagnostics.json",output)
    print(json.dumps({k:v for k,v in output.items() if k not in ("per_case",)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
