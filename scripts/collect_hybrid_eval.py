"""Create a new blinded hybrid pool. Never overwrite an existing benchmark."""
import argparse, hashlib, importlib.metadata, json, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
sys.path.insert(0,str(ROOT/'scripts'))
from app.data_preparation.history_io import file_hash, write_json
from app.data_preparation.retrieval_bundle import load_index
from app.data_preparation.e5_bundle import load_e5_vectors
from app.ml.e5_retriever import LocalE5Encoder
from app.ml.bm25_retriever import BM25Retriever
from app.ml.hybrid_retriever import HybridRetriever
from app.ml.retrieval_baselines import topic_baseline
from search_materials import context_for_case
import torch


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases', type=Path, default=ROOT/'data/interim/retrieval_eval/cases.json')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'data/interim/hybrid_eval_v1')
    parser.add_argument('--semantic-threshold',type=float,required=True)
    parser.add_argument('--judged-case-ids',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError('Evaluation directory exists; create a new version')
    torch.set_num_threads(4)
    index, manifest=load_index(ROOT/'artifacts/retrieval')
    for name,expected in manifest['code_sha256'].items():
        raw=(ROOT/name).read_bytes()
        hashes={hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()}
        if expected not in hashes: raise ValueError('Search code differs from frozen index: '+name)
    encoder=LocalE5Encoder(ROOT/'artifacts/e5-model')
    semantic, em=load_e5_vectors(index,manifest,encoder,ROOT/'artifacts/e5-vectors')
    bm25=BM25Retriever().fit(list(index.materials.values()),index.rows)
    hybrid=HybridRetriever(semantic,bm25,semantic_threshold=args.semantic_threshold)
    cases=json.loads(args.cases.read_text(encoding='utf-8'))
    selected=json.loads(args.judged_case_ids.read_text(encoding='utf-8'))
    known={case['case_id']:case for case in cases}
    if len(set(selected))!=len(selected) or any(k not in known or known[k]['behavior'] for k in selected):
        raise ValueError('Invalid relevance subset')
    if {known[k]['split'] for k in selected} != {'dev','test'}:raise ValueError('Both splits required')
    freeze={'source_cases_sha256':file_hash(args.cases),'judged_subset_sha256':file_hash(args.judged_case_ids),'index_bundle_id':manifest['bundle_id'],
            'e5_vectors_sha256':em['vectors_sha256'],'semantic_threshold':args.semantic_threshold,
            'fusion':'rrf-60-equal-weights-v2','minimum_query_coverage':0.3,'scope':'exploratory; scenarios authored by implementer; independent review pending',
            'runtime_versions':{name:importlib.metadata.version(name) for name in ('numpy','scikit-learn','torch','transformers','tokenizers')},
            'code_sha256':{str(path.relative_to(ROOT)):file_hash(path) for path in sorted(
                list((ROOT/'backend/app/ml').glob('*.py')) + list((ROOT/'backend/app/data_preparation').glob('*.py')) +
                [ROOT/'scripts/search_materials.py', ROOT/'scripts/collect_hybrid_eval.py', ROOT/'scripts/evaluate_hybrid_eval.py'])}}
    args.output_dir.mkdir(parents=True,exist_ok=False)
    (args.output_dir/'judged_subset.json').write_bytes(args.judged_case_ids.read_bytes())
    (args.output_dir/'cases.json').write_bytes(args.cases.read_bytes())
    if file_hash(args.output_dir/'cases.json') != freeze['source_cases_sha256']:
        raise ValueError('Case copy checksum mismatch')
    write_json(args.output_dir/'freeze.json',freeze)
    by_id={row.chunk_id:row for row in index.rows}
    rankings=[]; pools=[]
    for case in cases:
        context=context_for_case(case)
        methods={}
        for name,func in [('tfidf',lambda: index.query(context,50)),('topic',lambda: topic_baseline(index,context,50)),
                          ('bm25',lambda: bm25.query(context,50)),('e5',lambda: semantic.query(context,50)),
                          ('hybrid',lambda: hybrid.query(context,50))]:
            start=time.perf_counter(); result=func(); latency=(time.perf_counter()-start)*1000
            if name in ('tfidf','topic'):
                rows=[(c.material_key,c.retrieval_score,by_id[c.evidence_chunk_id]) for c in result.candidates]
            elif name=='hybrid':
                rows=[(key,score,next(iter(evidence.values()))['chunk']) for key,score,evidence in result]
            else: rows=result
            methods[name]={'keys':[key for key,_,_ in rows],'latency_ms':latency}
            methods[name]['evidence']={key:chunk.chunk_id for key,_,chunk in rows[:10]}
        rankings.append({'case':case,'methods':methods})
        if case['case_id'] not in selected: continue
        keys=set() if case['behavior'] else {key for method in methods.values() for key in method['keys'][:10]}
        cards=[]
        for key in sorted(keys):
            m=index.materials[key]
            chunks={index._metadata_row(key).chunk_id}
            chunks.update(method['evidence'][key] for method in methods.values() if key in method['evidence'])
            cards.append({'material_key':key,'title':m.title,'item_type':m.item_type,'topics':m.topics,
                          'tags':m.tags,'access_type':m.access_type,'listed_price':m.listed_price,
                          'price_unknown':m.listed_price is None,'duration_minutes':m.duration_minutes,
                          'duration_unknown':m.duration_minutes is None,'url_state':m.url_state,
                          'public_evidence':[by_id[c].text for c in sorted(chunks)]})
        if case['case_id'] in selected: pools.append({'case':case,'cards':cards})
        print('Prepared case',case['case_id'],flush=True)
    write_json(args.output_dir/'rankings.json',rankings)
    write_json(args.output_dir/'blind_pool.json',pools)
    files = ('cases.json', 'judged_subset.json', 'freeze.json', 'rankings.json', 'blind_pool.json')
    write_json(args.output_dir/'collection_manifest.json', {'files': {name: file_hash(args.output_dir/name) for name in files}})
    print('Prepared',len(cases),'cases')
if __name__=='__main__':main()