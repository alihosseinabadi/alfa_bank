"""Diagnostic simulator: synthetic contexts, nonlinear outcome and delayed telemetry."""
import json, numpy as np
from app.ml.linucb import SharedLinUCB

def run(seed, scenario, method, rounds=120):
 rng=np.random.default_rng(seed); x=rng.uniform(-1,1,(rounds,6,4)); u=rng.random((rounds,6)); user=rng.normal(size=4); flip=rng.normal(size=4)
 model=SharedLinUCB(5,alpha=.5 if method=='ucb' else 0); pending=[]; total=regret=0.
 for t in range(rounds):
  for due,vec,reward in pending[:]:
   if due<=t: model.observe(vec,reward); pending.remove((due,vec,reward))
  w=flip if scenario=='change' and t>=rounds//2 else user
  if scenario=='new_users': w=user if t%2==0 else flip
  X=np.column_stack((np.ones(6),x[t])); z=x[t]@w+x[t,:,0]*x[t,:,1]-2
  prob=1/(1+np.exp(-z)); scores=X[:,1] if method=='prior' else [model.score(v).total for v in X]
  j=int(np.argmax(scores)); reward=float(u[t,j]<prob[j]); total+=reward; regret+=float(max(prob)-prob[j])
  missing=scenario=='missing' and rng.random()<.5
  if not missing: pending.append((t+(int(rng.integers(5,20)) if scenario=='delayed' else 1),X[j].tolist(),reward))
 return total,regret

out={}
for scenario in ('sparse','delayed','change','new_users','missing'):
 out[scenario]={}
 for method in ('prior','greedy','ucb'):
  values=np.array([run(seed,scenario,method) for seed in range(10)])
  out[scenario][method]={'reward_mean':float(values[:,0].mean()),'regret_mean':float(values[:,1].mean()),'reward_seed_interval_2_5_97_5':np.quantile(values[:,0],[.025,.975]).tolist(),'per_seed':values.tolist()}
print(json.dumps({'scenarios':out,'warning':'synthetic; no causal business conclusion'},indent=2))
