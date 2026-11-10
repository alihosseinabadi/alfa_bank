# experiments/

Offline simulation and evaluation. This is where we **prove** the algorithm before
trusting it in the API.

## Files

| File | Responsibility |
|---|---|
| `synthetic_users.py` | generate users with hidden preference vectors |
| `environment.py` | one round: retrieve -> policy -> simulated feedback -> reward |
| `random_baseline.py` | uniform random policy over candidates |
| `popularity_baseline.py` | top popular from past window only |
| `bandit_experiment.py` | LinUCB policy across rounds and seeds |
| `metrics.py` | reward, regret, CTR, conversion, precision/recall/NDCG@K |
| `plots.py` | write PNGs to `experiments/outputs/` |

## Why it exists

Real traffic does not exist in a hackathon. A simulator lets us:

- compare policies under identical conditions,
- run many seeds and report confidence intervals,
- compute regret, which needs an oracle that knows hidden preferences,
- iterate on features, alpha and rewards without touching a database.

## Simulator contract

```python
user = {
  "user_id": 101,
  "industry": "marketing",
  "business_stage": "growth",
  "hidden_preferences": {"marketing": 0.95, "sales": 0.85, "finance": 0.20},
}
```

`hidden_preferences` is **never** passed to a policy. Only `environment.py` uses it to
generate feedback and to compute the oracle.

## Fairness invariants

- Same candidate set per round for all policies.
- Same users across policies (same seed).
- Popularity from past data only.
- Same reward engine.

Any violation invalidates the comparison.

## Run

```bash
python scripts/run_experiments.py --users 200 --rounds 50 --seeds 5
```

Outputs: a results table in the console and PNGs in `experiments/outputs/`.

## Honesty

Every result is **simulated**. Charts are labelled as such. We never present synthetic
lift as real Alfa-Kurs performance.

## What to learn

Experimental design, baselines, reproducibility with seeds, and why regret requires
counterfactual knowledge.
