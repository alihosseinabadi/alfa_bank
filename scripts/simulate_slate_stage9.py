"""Synthetic slate simulation, no inference about production or sales."""
import json, math
import numpy as np
from app.ml.linucb import SharedLinUCB
from app.ml.slate_policy import replay_record

def run(seed, policy, rounds=120, k=3):
    rng=np.random.default_rng(seed)
    contexts=rng.uniform(-1,1,(rounds,8,4)); draws=rng.random((rounds,8)); delay=rng.integers(1,6,(rounds,8))
    formats=rng.integers(0,3,(rounds,8)); user=rng.normal(size=4)
    chooser=np.random.default_rng(seed+89127)
    learner=SharedLinUCB(5,alpha=.5)
    pending=[]; total=0.; regret=0.; diversity=0.; relevance=0.
    for t in range(rounds):
        due=[x for x in pending if x[0]<=t]; pending=[x for x in pending if x[0]>t]
        for _,x,r in due: learner.observe(x,r)
        X=np.column_stack((np.ones(8),contexts[t])); z=contexts[t]@user+contexts[t,:,0]*contexts[t,:,1]-2.0
        truth=1/(1+np.exp(-z))
        ucb=np.array([learner.score(x).total for x in X]) if policy!='prior' else contexts[t,:,0]
        prior=(contexts[t,:,0]+1)/2
        selected=[]
        if policy == 'slate':
            pool=[{'material_key':str(i),'prior_score':float(prior[i]),'ucb_score':float(ucb[i]),'item_type':str(formats[t,i]),'retrieval_rank':i+1} for i in range(8)]
            record={'pool':pool,'relevance_gap':.15,'epsilon':.1,'diversity_weight':.05,'requested_k':k,'seed':int(chooser.integers(0,2**63))}
            selected=[int(key) for key,prob in replay_record(record)]
        else:
            selected=sorted(range(8),key=lambda i:(-ucb[i],i))[:k]
        total+=sum(float(draws[t,i]<truth[i]) for i in selected)
        relevance+=sum(truth[i] for i in selected)/k
        diversity+=len({int(formats[t,i]) for i in selected})/k
        regret+=float(sum(sorted(truth,reverse=True)[:k])-sum(truth[i] for i in selected))
        for i in selected: pending.append((t+int(delay[t,i]),X[i].tolist(),float(draws[t,i]<truth[i])))
    return {'reward':total,'regret':regret,'relevance':relevance/rounds,'diversity':diversity/rounds}

def main():
    result={}
    for name in ('prior','ucb','slate'):
        samples=[run(seed,name) for seed in range(10)]
        result[name]={key:{'mean':float(np.mean([v[key] for v in samples])),'std':float(np.std([v[key] for v in samples],ddof=1))} for key in samples[0]}
        result[name]['per_seed']=samples
    print(json.dumps({'note':'synthetic users; slate uses production replay_record; no sales inference','rounds':120,'seeds':10,'results':result},indent=2))
if __name__=='__main__':main()
