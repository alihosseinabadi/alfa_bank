"""Synthetic nonlinear delayed-feedback comparison; no inference about real sales."""
import json
import numpy as np
from app.ml.linucb import SharedLinUCB

def run(seed, method, rounds=150):
    rng = np.random.default_rng(seed)
    contexts = rng.uniform(-1,1,(rounds,6,4))
    uniform = rng.random((rounds,6))
    delays = rng.integers(1, 6, rounds)
    user = rng.normal(size=4)
    model = SharedLinUCB(5, alpha=0.6 if method=='linucb' else 0.0)
    pending = []
    reward = regret = 0.0
    for t in range(rounds):
        for due, x, y in pending[:]:
            if due <= t:
                model.observe(x,y); pending.remove((due,x,y))
        X = np.column_stack((np.ones(6),contexts[t]))
        z = contexts[t] @ user + 1.2 * contexts[t,:,0] * contexts[t,:,1] - 1.8
        probs = 1 / (1 + np.exp(-z))
        scores = X[:,1] if method=='prior' else np.array([model.score(x).total for x in X])
        selected = int(np.argmax(scores))
        y = float(uniform[t,selected] < probs[selected])
        reward += y
        regret += float(probs.max() - probs[selected])
        # Every result matures after a delay; zeros are observed only then.
        pending.append((t+int(delays[t]), X[selected].tolist(), y))
    return reward, regret

def main():
    out = {}
    for method in ('prior','greedy','linucb'):
        values = np.array([run(seed, method) for seed in range(10)])
        out[method] = {'mean_reward':float(values[:,0].mean()), 'mean_expected_regret':float(values[:,1].mean()), 'per_seed':values.tolist()}
    print(json.dumps({'seeds':10,'rounds':150,'environment':'synthetic nonlinear delayed sparse feedback','results':out}, indent=2))
if __name__ == '__main__': main()
