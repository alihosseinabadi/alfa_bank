import sys,json
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'backend'),str(R/'scripts')]
from app.data_preparation.ranking_bundle import load_ranking_catalog,load_ranking_context
from app.ml.profile_contracts import ExplicitConstraints
from app.ml.prior_ranking import rank_candidates
from app.ml.linucb import SharedLinUCB
from app.ml.ucb_ranking import rank_ucb
from app.ml.slate_policy import select_slate
from app.ml.feature_registry import FEATURE_DIMENSION
from rank_materials import retrieve_batch
from types import SimpleNamespace
idx,meta,mats=load_ranking_catalog(R/'artifacts/retrieval',R/'data/processed/catalog')
cases=json.loads((R/'data/interim/quality_stage56/cases.json').read_text())
labels=json.loads((R/'data/interim/quality_stage56/pool_judgments.json').read_text())
judges={(x['case_id'],x['material_key']):x['grade'] for x in labels}
model=SharedLinUCB(FEATURE_DIMENSION);model.state_id='empty-test';model.matrix_digest=model.state_digest()
out={str(g):{'shown':0,'judged':0,'positive':0,'success_cases':0,'cases':0} for g in [.15,.40,.50,.60,.70]}
for x in cases:
 if x['split']!='dev' or not x['case_id'].startswith('dev'):continue
 const=ExplicitConstraints(formats=x.get('formats') or [],available_time_minutes=x.get('available_time_minutes'),budget_preference=x.get('budget_preference'))
 p,ctx,progress=load_ranking_context(mats,meta,x['task'],const)
 batch=retrieve_batch(idx,meta,ctx,SimpleNamespace(method='tfidf'))
 prior=rank_candidates(batch,mats,ctx,profile=p,progress=progress,k=50)
 if not prior.candidates:continue
 ucb=rank_ucb(prior,model,model.state_id)
 for gap in [.15,.40,.50,.60,.70]:
  for seed in range(10):
   r=select_slate(ucb,seed=seed,k=6,relevance_gap=gap);a=out[str(gap)];a['cases']+=1;a['shown']+=len(r.candidates)
   grades=[judges[(x['case_id'],y.material_key)] for y in r.candidates if (x['case_id'],y.material_key) in judges]
   a['judged']+=len(grades);a['positive']+=sum(g>=2 for g in grades);a['success_cases']+=int(any(g>=2 for g in grades))
for gap,a in out.items():
 a['mean_size']=a['shown']/a['cases'];a['judged_coverage']=a['judged']/a['shown'];a['judged_positive_rate']=a['positive']/a['judged'] if a['judged'] else None;a['known_success']=a['success_cases']/a['cases']
for a in out.values():
 a['seed_evaluations']=a.pop('cases')
 a['independent_cases']=a['seed_evaluations']//10
print(json.dumps(out,indent=2))
