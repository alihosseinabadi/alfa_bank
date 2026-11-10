# Evaluation Methodology

How we prove the recommendation engine works — honestly, reproducibly, and against
fair baselines.

---

## 1. What we are proving

Not "the UI is nice". We prove:

1. LinUCB collects more reward than random and popularity under identical conditions.
2. The gap is stable across random seeds (not one lucky run).
3. The ranking is good by ranking metrics (precision/recall/NDCG), not only by reward.
4. Exploration is real and decreases over time, as expected.

## 2. Fairness rules

- **Same candidates** for all policies in a round (same retrieval output).
- **Same simulated users** across policies (same seed, same hidden preferences).
- **Same reward engine** for all policies.
- **Popularity uses past data only** — never the evaluation window.
- **The policy never sees hidden preferences.** Only the simulator does, and only to
  generate feedback / compute the oracle.

If any of these is violated, the comparison is void. Each is covered by a test.

## 3. Metrics

### Cumulative reward
Sum of rewards over rounds. Higher is better.

```
R(T) = Σₜ rₜ
```

### Cumulative regret
Gap to an oracle that always picks the best course for the user's hidden preferences.

```
regret(T) = Σₜ ( r*ₜ − rₜ )
```

Lower is better. Regret is only computable in simulation, because it needs the
counterfactual best action.

### CTR
```
CTR = clicks / impressions
```

### Conversion
```
conversion = purchases / impressions
```

Both require impressions to be logged at display time.

### Precision@K / Recall@K
```
precision@K = relevant items in top K / K
recall@K    = relevant items in top K / all relevant items
```
"Relevant" = course category matches the user's top preferences.

### NDCG@K
```
DCG@K  = Σᵢ₌₁ᴷ relᵢ / log₂(i + 1)
NDCG@K = DCG@K / IDCG@K
```
Rewards good items appearing earlier.

### Exploration vs exploitation
```
exploration_share = non-greedy picks / total picks
```
Should start high and decay as `A` accumulates information.

## 4. Protocol

```bash
python scripts/run_experiments.py --users 200 --rounds 50 --seeds 5
```

For each seed:

1. Generate users from the simulator.
2. For each round: retrieve candidates, each policy selects, simulator responds,
   rewards applied, metrics recorded.
3. Store per-seed curves.

Aggregate across seeds:

- report **mean**
- report **95% confidence interval** (t-based for small seed counts)

Never report a single seed.

## 5. Reporting format

| Policy | Cum. reward (mean ± CI) | CTR | Conversion | NDCG@10 |
|---|---|---|---|---|
| Random | ... | ... | ... | ... |
| Top Popular | ... | ... | ... | ... |
| LinUCB | ... | ... | ... | ... |

Every table and chart is labelled **simulated**.

## 6. Plots (saved to `experiments/outputs/`)

1. Cumulative reward vs round (three lines).
2. Cumulative regret vs round (three lines).
3. CTR over time.
4. Conversion over time.
5. Exploration share over time.
6. NDCG@10 distribution across seeds (boxplot).

## 7. Sanity checks before trusting results

- [ ] Random policy's CTR is roughly the base rate of clicks.
- [ ] Popular policy beats random (it should, if popularity is informative).
- [ ] LinUCB beats popular (that is the claim being tested).
- [ ] Regret grows sub-linearly for LinUCB, near-linearly for random.
- [ ] Exploration share decays.
- [ ] Increasing rounds improves LinUCB's margin over popular.
- [ ] Changing the seed does not flip the ordering.

If LinUCB does **not** beat popular, do not hide it: investigate features, `α`,
reward scaling, or candidate quality, and document what changed.

## 8. Threats to validity

| Threat | Effect | Mitigation |
|---|---|---|
| Simulator too simple | optimistic results | document assumptions, vary noise |
| Hidden preference leakage | fake lift | code review + test that policy inputs exclude them |
| Future leakage in popularity | baseline too strong/weak | windowed query, test |
| Single seed | noise mistaken for signal | 5+ seeds, CI |
| Over-tuning α on test | overfit demo | tune on a separate seed set |
| Position bias | CTR inflated at top | acknowledge; future work |

## 9. Honesty rules

- All numbers are **simulated**.
- We never claim real conversion improvements.
- We publish the simulator parameters so others can reproduce or challenge them.
- If a baseline wins on a metric, we say so.
