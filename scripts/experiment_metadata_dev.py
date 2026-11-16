import sys,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'backend'),str(R/'scripts')]
if not (R/'backend/app/ml/light_hybrid.py').exists() or not (R/'data/synthetic/light_benchmark_v1/queries.json').exists():
 raise SystemExit('Experiment requires light-hybrid-search-v2 and light_benchmark_v1 from lead 01aa4ba; they are not part of this branch.')
from app.ml.light_hybrid import LightHybridRetrieverV2
from app.ml.ru_normalize import analyze
from app.ml.retrieval_metrics import judged_metrics
from evaluate_light_retrieval import load_benchmark
from search_materials import context_for_case
m,c,q,_=load_benchmark(); e=LightHybridRetrieverV2().fit(m,c)
cases=[x for x in q['cases'] if x['split']=='dev' and x['intent']=='relevance']
out={}; print('cases',len(cases),flush=True)
for weights in [(0,0),(.01,.005),(.025,.01),(.05,.02)]:
 vals=[];wins=0
 for x in cases:
  ctx=context_for_case(x); res=e.query(ctx,50); toks=set(analyze(ctx.query_text,e.dictionary.canonical_map))
  ranked=[]
  for card in res.candidates:
   mat=e.materials[card.material_key]; tt=set(analyze(mat.title,e.dictionary.canonical_map)); tp=set(analyze(' '.join(mat.topics),e.dictionary.canonical_map))
   score=card.retrieval_score+weights[0]*len(toks&tt)/max(1,len(toks))+weights[1]*len(toks&tp)/max(1,len(toks))
   ranked.append((card.material_key,score))
  ranked.sort(key=lambda pair:(-pair[1],next(i for i,c in enumerate(res.candidates) if c.material_key==pair[0])))
  vals.append(judged_metrics([key for key,_ in ranked],x['grades'],10))
 out[str(weights)]={'ndcg':float(np.mean([x['ndcg10'] for x in vals])),'success':float(np.mean([x['success5'] for x in vals]))}
print(json.dumps(out,indent=2),flush=True)
