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
| `metrics.py` | reward, regret, CTR, inspection rate, conversion, precision/recall/NDCG@K, CI |
| `plots.py` | write PNGs to `experiments/outputs/` |

## Why it exists

Real traffic does not exist in a hackathon. A simulator lets us:

- compare policies under identical conditions,
- run ≥10 seeds and report confidence intervals,
- compute regret, which needs an oracle that knows hidden preferences,
- iterate on features, alpha and rewards without touching a database.

## Simulator contract

```python
user = {
  "user_id": 101,
  "industry": "marketing",
  "business_stage": "growth",
  "experience": "some",
  "budget_sensitivity": 0.4,
  "goals": ["increase revenue", "hire first salesperson"],
  "hidden_preferences": {"marketing": 0.95, "sales": 0.85, "finance": 0.20},
}
```

`hidden_preferences` is **never** passed to a policy or to the feature builder. Only
`environment.py` uses it to generate feedback and to compute the oracle.

## Fairness invariants

- Same candidate set per round for all policies.
- Same users across policies (same seed).
- Popularity from the past window only (`shown_at < window_start`).
- Same reward engine instance.
- Oracle exists only in the simulator.

Each invariant has a test: `backend/tests/test_evaluation.py` and
`backend/tests/test_leakage.py`. If one fails, any result is void.

## Metrics

Reported separately, never blended:

```
CTR                    = clicks    / impressions
free_material_inspection_rate = inspects / impressions
purchase_conversion    = purchases / impressions
```

Plus cumulative reward, cumulative regret, NDCG@K, exploration share — mean and 95%
confidence interval across seeds.

## Run

```bash
python scripts/run_experiments.py --users 200 --rounds 50 --seeds 10
```

Outputs: a results table in the console and PNGs in `experiments/outputs/`, plus
`run_manifest.json` recording seeds and parameters.

## Honesty

Every result is **simulated**, using a **synthetic** catalogue and simulated users.
Charts are labelled as such. We never present synthetic lift as real Alfa-Kurs
performance. See [`docs/data_provenance.md`](../docs/data_provenance.md).

## What to learn

Experimental design, baselines, reproducibility with seeds, confidence intervals,
and why regret requires counterfactual knowledge that only a simulator can provide.
