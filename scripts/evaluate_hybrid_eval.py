"""Score a previously frozen blinded hybrid evaluation after local adjudication."""
import argparse, json, statistics, sys
import numpy as np
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.data_preparation.history_io import file_hash, write_json
from app.ml.retrieval_metrics import judged_metrics


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--eval-dir',type=Path,default=ROOT/'data/interim/hybrid_eval_v1')
    parser.add_argument('--case-ids',type=Path,help='Explicit fully judged subset; report separately')
    parser.add_argument('--output',type=Path,help='New report filename in the evaluation directory')
    args=parser.parse_args(); root=args.eval_dir
    collection=json.loads((root/'collection_manifest.json').read_text(encoding='utf-8'))
    if set(collection['files']) != {'cases.json', 'judged_subset.json', 'freeze.json', 'rankings.json', 'blind_pool.json'}:
        raise ValueError('Incomplete collection manifest')
    if any(file_hash(root/name) != digest for name,digest in collection['files'].items()):
        raise ValueError('Frozen collection checksum mismatch')
    freeze=json.loads((root/'freeze.json').read_text(encoding='utf-8'))
    rows=json.loads((root/'rankings.json').read_text(encoding='utf-8'))
    pool=json.loads((root/'blind_pool.json').read_text(encoding='utf-8'))
    labels=json.loads((root/'pool_judgments.json').read_text(encoding='utf-8'))
    known={entry['case']['case_id']:{card['material_key'] for card in entry['cards']} for entry in pool}
    if args.case_ids:
        selected=json.loads(args.case_ids.read_text(encoding='utf-8'))
        if len(set(selected))!=len(selected) or any(case not in known for case in selected):raise ValueError('Invalid evaluated subset')
        known={case:known[case] for case in selected}
    judgments=defaultdict(dict)
    for label in labels:
        case,key,grade=label['case_id'],label['material_key'],label['grade']
        if case not in known or key not in known[case] or type(grade) is not int or grade not in (0,1,2,3):
            raise ValueError('Invalid case, material or judgment grade')
        if key in judgments[case]: raise ValueError('Duplicate judgment')
        judgments[case][key]=grade
    if any(set(judgments[case]) != keys for case,keys in known.items()):
        raise ValueError('Every blinded card requires a judgment')
    per_case=[]
    for row in rows:
        case=row['case']; case_id=case['case_id']
        if case_id not in known: continue
        for name,method in row['methods'].items():
            keys=method['keys']; entry={'case_id':case_id,'split':case['split'],'method':name,
                'returned':len(keys),'latency_ms':method['latency_ms'],'behavior':case['behavior']}
            if case['behavior']:
                entry['behavior_passed'] = not keys
            else:
                entry.update(judged_metrics(keys,judgments[case_id]))
            per_case.append(entry)
    summary={}
    for split in ('dev','test'):
        summary[split]={}
        for method in ('tfidf','topic','bm25','e5','hybrid'):
            group=[r for r in per_case if r['split']==split and r['method']==method]
            relevance=[r for r in group if not r['behavior']]
            behavior=[r for r in group if r['behavior']]
            summary[split][method]={metric:statistics.mean(r[metric] for r in relevance) for metric in ('ndcg10','success5','pooled_recall50')}
            summary[split][method].update({'cases':len(relevance),'empty_behavior_passed':sum(r['behavior_passed'] for r in behavior),'behavior_cases':len(behavior)})
    latency={}
    for method in ('tfidf','topic','bm25','e5','hybrid'):
        values=[r['latency_ms'] for r in per_case if r['method']==method]
        latency[method]={'queries':len(values),'p50_ms':float(np.percentile(values,50)),'p95_ms':float(np.percentile(values,95))}
    result={'freeze':freeze,'summary':summary,'latency':latency,'per_case':per_case,
            'judgments_sha256':file_hash(root/'pool_judgments.json'),'scorer_sha256':file_hash(Path(__file__)),
            'limitations':['Exploratory comparison, not an independently locked test.',
             'Relevance depends on local assessors and incomplete top-10 pooled judgments.',
             'No online A/B test, conversion or business lift is measured.']}
    output=root/(args.output.name if args.output else 'evaluation.json')
    if args.case_ids: result['subset_sha256']=file_hash(args.case_ids)
    if output.exists(): raise FileExistsError('Evaluation exists; use a new version')
    write_json(output,result)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()