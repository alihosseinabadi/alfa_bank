"""IPS for single-slot logged decisions with explicit finite action supports."""
import math

def ips(rows):
    if not rows: raise ValueError('empty sample')
    weighted, weights = [], []
    for row in rows:
        behavior, target, chosen, reward = row['behavior'], row['target'], row['chosen'], row['reward']
        if set(target) - set(behavior): raise ValueError('target lacks behavior support')
        for distribution in (behavior,target):
            if not distribution or any(not math.isfinite(x) or x < 0 or x > 1 for x in distribution.values()) or not math.isclose(sum(distribution.values()),1,abs_tol=1e-9):
                raise ValueError('invalid distribution')
        if any(prob > 0 and behavior.get(key,0) <= 0 for key,prob in target.items()): raise ValueError('target lacks behavior support')
        if chosen not in behavior or behavior[chosen] <= 0 or not math.isfinite(reward) or not 0 <= reward <= 1: raise ValueError('invalid observation')
        weight=target.get(chosen,0)/behavior[chosen]
        weights.append(weight); weighted.append(weight*reward)
    mean=sum(weighted)/len(weighted)
    variance=sum((x-mean)**2 for x in weighted)/(len(weighted)-1) if len(weighted)>1 else None
    denom=sum(w*w for w in weights)
    return {'ips':mean,'sample_variance':variance,'effective_sample_size':sum(weights)**2/denom if denom else 0.0,'count':len(rows),'max_weight':max(weights)}
