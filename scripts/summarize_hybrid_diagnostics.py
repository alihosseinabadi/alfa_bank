"""Summarize frozen retrieval constraints and timing without relevance judgments."""
import argparse,json,statistics,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
from app.data_preparation.history_io import file_hash,write_json
from app.data_preparation.retrieval_bundle import load_index
from app.ml.tfidf_retriever import eligible_for_context
from search_materials import context_for_case

def main():
    p=argparse.ArgumentParser();p.add_argument('--eval-dir',type=Path,default=ROOT/'data/interim/hybrid_eval_v1');args=p.parse_args();root=args.eval_dir
    collection=json.loads((root/'collection_manifest.json').read_text(encoding='utf8'))
    if any(file_hash(root/name)!=digest for name,digest in collection['files'].items()):raise ValueError('Frozen collection checksum mismatch')
    freeze=json.loads((root/'freeze.json').read_text(encoding='utf8'))
    idx,manifest=load_index(ROOT/'artifacts/retrieval')
    if manifest['bundle_id']!=freeze['index_bundle_id']:raise ValueError('Index mismatch')
    rows=json.loads((root/'rankings.json').read_text(encoding='utf8'))
    summary={}
    for name in ('tfidf','topic','bm25','e5','hybrid'):
        entries=[]
        for row in rows:
            case=row['case'];ctx=context_for_case(case);method=row['methods'][name]; keys=method['keys']
            entries.append({'returned':len(keys),'unique':len(keys)==len(set(keys)),
                'valid_count':len(keys)<=50,'eligible':all(k in idx.materials and eligible_for_context(idx.materials[k],ctx) for k in keys),
                'behavior':bool(case['behavior']),'behavior_passed':not keys,'latency':method['latency_ms']})
        times=[r['latency'] for r in entries]; behavior=[r for r in entries if r['behavior']]
        summary[name]={'queries':len(entries),'no_results':sum(r['returned']==0 for r in entries),
            'behavior_cases':len(behavior),'behavior_without_results':sum(r['behavior_passed'] for r in behavior),
            'all_constraints_passed':all(r['unique'] and r['valid_count'] and r['eligible'] for r in entries),
            'latency_p50_ms':float(np.percentile(times,50)),'latency_p95_ms':float(np.percentile(times,95))}
    result={'summary':summary,'collection_manifest_sha256':file_hash(root/'collection_manifest.json'),
            'limits':['No relevance labels or business lift are inferred.','Timing excludes model loading and service integration.']}
    out=root/'diagnostics.json'
    if out.exists():raise FileExistsError('Diagnostics already exists')
    write_json(out,result);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()