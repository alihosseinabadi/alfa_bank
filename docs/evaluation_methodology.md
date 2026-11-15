# Evaluation Methodology

How we prove the recommendation engine works — reproducibly, fairly, and honestly.

---

## 1. What we are proving

Not "the UI is nice". We prove:

1. LinUCB collects more reward than random and popularity under **identical** conditions.
2. The gap is stable across **at least 10 seeds** (not one lucky run).
3. Ranking quality improves by ranking metrics (precision/recall/NDCG), not only reward.
4. Exploration is real and decays as evidence accumulates.

## 2. Fairness invariants (each has a test)

| Invariant | Enforced by | Test |
|---|---|---|
| Same simulated users for every policy | one user population generated per seed, shared | `test_evaluation.py::test_identical_users` |
| Same candidate set per round for every policy | retrieval runs once per (user, round), result reused | `test_evaluation.py::test_identical_candidates` |
| Same reward engine for every policy | one `reward_engine` instance, passed in | `test_evaluation.py::test_same_reward_engine` |
| Popularity uses **past data only** | window query `shown_at < window_start` | `test_leakage.py::test_popularity_window` |
| Policies never see hidden preferences | feature builder takes only observable fields | `test_leakage.py::test_no_hidden_preferences_in_features` |
| Oracle used only inside the simulator | oracle lives in `experiments/`, never importable by `ml/` | `test_leakage.py::test_oracle_not_imported_by_ml` |

If any invariant is violated, the comparison is void. Tests run in CI, not just in prose.

## 3. Reproducibility

```bash
python scripts/run_experiments.py --users 200 --rounds 50 --seeds 10 --seed-base 42
```

- Default **10 seeds** (seeds `42..51`), configurable up to whatever is computationally practical.
- Every random source is seeded: user generation, simulator noise, policy tie-breaking,
  retrieval shuffling.
- `data/synthetic/run_manifest.json` records seeds, parameters, feature version and timestamp.
- Two runs with the same manifest must produce byte-identical metric tables.

If compute does not allow 10 seeds for a large configuration, reduce `--users`/`--rounds`
**and record the reduction in the manifest** — never silently drop seeds.

## 4. Metrics

### 4.1 Reward and regret

```
cumulative_reward(T) = Σₜ rₜ
regret(T)            = Σₜ (r*ₜ − rₜ)
```

`r*ₜ` is the reward of the best candidate for that user's hidden preferences — computed
by the **oracle inside the simulator only**. Regret is undefined outside simulation.

### 4.2 Three separate funnel metrics

Reported independently, never blended:

```
CTR                    = clicks              / impressions
free_material_inspection_rate = inspects      / impressions
purchase_conversion    = purchases           / impressions
```

Why separate: a policy can win CTR by showing clickbait and lose purchase conversion.
Blending them would hide exactly the failure we care about.

Secondary funnel ratios (diagnostic only):

```
click_to_inspect  = inspects  / clicks
inspect_to_purchase = purchases / inspects
```

### 4.3 Ranking metrics

```
precision@K = |relevant ∩ topK| / K
recall@K    = |relevant ∩ topK| / |relevant|
DCG@K       = Σᵢ₌₁ᴷ relᵢ / log₂(i + 1)
NDCG@K      = DCG@K / IDCG@K
```

"Relevant" = course category is in the user's top-2 preferred categories. This is a
simulator-side label, used for scoring only — never as a model input.

### 4.4 Exploration vs exploitation

```
exploration_share = non_greedy_picks / total_picks
```

A pick is "non-greedy" when the chosen action is not the argmax of the exploit term
alone. Should start high and decay.

## 5. Protocol

For each seed `s` in `42..51`:

1. Generate the user population from `s`.
2. Split the interaction timeline into a **warm-up window** and an **evaluation window**.
3. For each round in the evaluation window, for each user:
   - retrieve candidates **once** and give the identical list to every policy;
   - each policy selects one course;
   - the simulator samples click / inspect / purchase from hidden preferences;
   - reward is computed by the shared reward engine;
   - metrics are appended to that policy's per-seed curve.
4. Popularity inside the evaluation window is computed from the warm-up window only.

Aggregate across seeds:

- report **mean**
- report **95% confidence interval** using the t-distribution for small `n`
  (`scipy.stats.t.ppf(0.975, n-1) * std / sqrt(n)`), or a documented bootstrap if
  SciPy is not a dependency.

Never report a single seed. Never report a CI computed across rounds instead of
across seeds — rounds are not independent.

## 6. Reporting format

| Policy | Cum. reward (mean ± 95% CI) | CTR | Inspection rate | Conversion | NDCG@10 |
|---|---|---|---|---|---|
| Random | ... | ... | ... | ... | ... |
| Top Popular (past window) | ... | ... | ... | ... | ... |
| LinUCB | ... | ... | ... | ... | ... |

Every table and chart carries the label **simulated**.

## 7. Plots (`experiments/outputs/`)

1. Cumulative reward vs round (three lines, shaded CI).
2. Cumulative regret vs round (three lines).
3. CTR over time.
4. Free-material inspection rate over time.
5. Purchase conversion over time.
6. Exploration share over time.
7. NDCG@10 distribution across seeds (boxplot).

## 8. Test specifications

### `backend/tests/test_evaluation.py`
- identical user populations across policies for a given seed
- identical candidate lists across policies per round
- same reward engine instance used by all policies
- 10 seeds produce 10 independent result records
- mean/CI helper returns finite values and CI brackets the mean
- metric denominators: CTR is `clicks/impressions`, not `clicks/users`
- zero-impression guard: metrics return `None`/raise, never divide by zero

### `backend/tests/test_leakage.py`
- popularity baseline never reads events at or after `window_start`
- feature builder signature cannot accept `hidden_preferences` (inspect + call test)
- `ml/` does not import `experiments/` (import graph assertion)
- oracle object is not reachable from any policy constructor
- shuffled event order does not change past-window popularity

## 9. Sanity checks before trusting results

- [ ] Random CTR ≈ simulator base click rate.
- [ ] Popular beats random if popularity is informative.
- [ ] LinUCB beats popular on cumulative reward and NDCG@10.
- [ ] Regret grows sub-linearly for LinUCB, near-linearly for random.
- [ ] Exploration share decays.
- [ ] All 10 seeds preserve the ordering; a flipped seed is reported, not hidden.
- [ ] Metrics recomputed from the raw log match the reported table.

If LinUCB does **not** beat popular: do not hide it. Investigate features, `α`, reward
scaling or candidate quality, and document what changed and which seeds were used for
tuning versus reporting.

## 10. Threats to validity

| Threat | Effect | Mitigation |
|---|---|---|
| Simulator too simple | optimistic results | document assumptions, vary noise, report sensitivity |
| Hidden preference leakage | fake lift | import test + feature-builder signature test |
| Future leakage in popularity | invalid baseline | windowed query + leakage test |
| Single seed | noise as signal | ≥10 seeds, CI across seeds |
| Tuning α on reported seeds | overfit demo | tune on seeds 0–4, report on 42–51 |
| Position bias | CTR inflated at top | acknowledge, future work |
| Non-independent rounds | CI too narrow | CI computed across seeds only |

## 11. Honesty rules

- All numbers are **simulated**.
- Never claim real conversion improvements.
- Publish simulator parameters so others can reproduce or challenge them.
- If a baseline wins a metric, say so in the table and in the demo.

## 12. Retrieval evaluation on the public synthetic benchmark (added Phase 1)

Sections 1–11 describe how the *bandit* is evaluated inside a simulator. Retrieval is
a different question — it happens before any policy sees a candidate — and it needs a
different harness, because a candidate that retrieval misses can never be recovered
by ranking. Since the real catalog, indexes and judgments are not in this repository,
retrieval is evaluated on a public synthetic benchmark:

- generator: `scripts/make_light_benchmark.py` → `data/synthetic/light_benchmark_v1/`
- runner: `scripts/evaluate_light_retrieval.py`
- current results: `docs/light_search_evaluation.md`

### 12.1 Construction, and what it costs in validity

168 synthetic materials across 14 Russian business topics, 294 public chunks
(paid materials contribute metadata chunks only, so the paid-body rule stays
exercised). 104 cases: 84 relevance, 12 off-topic refusal, 8 constraint.

Relevance is **construction-derived**: the material a query was generated from is 2,
other materials of the same topic are 1, the rest are 0. Every material is graded, so
`judged_metrics` never sees an unjudged top-k.

Two query families per concept, both targeting the same material:

| family | purpose | known bias |
|---|---|---|
| `natural` | the concept's own wording | easy for any lexical engine; close to a title lookup |
| `paraphrase` | different wording, few shared surface forms | **built to favour morphology-aware retrieval** |

The `paraphrase` family is a stress test by construction. A gain on it is expected,
not discovered. It must always be reported next to `natural`, never merged into a
single "NDCG improved" claim.

### 12.2 Splitting and freezing

Split is assigned by salted hash of `case_id` (`HOLDOUT_SALT`, residues 0–2 of
`sha256(...) % 10`), i.e. **before** any result exists. Result: 73 dev / 31 holdout.

Freeze record (must accompany every table):

- `holdout_hash` = digest of the sorted holdout case ids
- `catalog.json` and `queries.json` sha256

Any change to the generator changes those hashes and invalidates every table that
quotes them. Numbers are only comparable within one hash triple.

### 12.3 Metrics and statistics

- **NDCG@10**, **Success@5** (any grade-2 in top 5), **pooled Recall@50**, via the
  existing `ml/retrieval_metrics.judged_metrics`.
- **Refusal rate** on off-topic cases: fraction where the engine returns no
  candidates. Reported per engine; the case count is small (9 dev / 3 holdout) and
  the CIs are correspondingly useless — read it as a smoke test.
- **False-refusal rate** on legitimate queries: fraction of relevance cases where the
  engine returned nothing. This is the cost side of the coverage guard and is
  reported explicitly.
- **Constraint violations**: count of returned materials that break a requested
  filter. This is an invariant, not an average: the number must be 0.
- **Latency**: warm p50/p95 per query at `k=50`, after one untimed pass.

Confidence intervals are **percentile bootstraps over cases** (2000 rounds, seed 7).
Cases are the independent unit; queries are not resampled within a case.

For the claims the report actually makes, marginal CIs are not enough: they overlap
easily at n≈25–59. The runner therefore also reports **paired differences** — the
bootstrap of `metric(engine A) − metric(engine B)` over the *same* cases, with
wins/losses/ties. "A is not worse than B" is only asserted when the paired CI
excludes zero in A's favour, or when the delta is ~0 with few losses.

### 12.4 Tuning rule

The fusion weights in `light-hybrid-search-v1` are hand-set defaults and were **not
tuned on the holdout**, nor swept on dev. If they are ever swept, the sweep runs on
dev only, the selected configuration is written down before the holdout is read, and
the report states how many configurations were tried. With 59 dev cases, a sweep that
moves NDCG by less than ~0.05 should be treated as noise, not as a finding.

### 12.5 What this harness cannot tell you

- real relevance for real entrepreneurs;
- behaviour at production scale (168 vs ≈1,444 materials);
- the value of E5 (no weights here);
- typos, personalisation, or multi-turn refinement (not in v1);
- annotator agreement (no human judgments exist here).

