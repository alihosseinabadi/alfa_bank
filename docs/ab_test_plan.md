# A/B test plan — light retrieval path

Scope: putting `light-hybrid-search-v1` in front of real users instead of
`tfidf-search-v1`. Companion documents: `docs/light_search_evaluation.md` (offline
evidence), `docs/evaluation_methodology.md` (§12), `docs/monitor_drift.md` tool
`scripts/monitor_drift.py`.

Status: **proposal**. Nothing in this document has been run against real traffic. The
offline evaluation is synthetic; it justifies testing, not shipping.

---

## 1. What is being tested, and what is not

| tested | not tested |
|---|---|
| retrieval: does the new engine surface materials users actually open? | the downstream bandit — held fixed at `shared-linucb-ranking-v1` in both arms |
| refusal behaviour on off-topic queries | UI, copy, or ranking presentation |
| latency in the live request path | E5 (not deployed; no weights) |

Only retrieval changes. Both arms go through the same prior ranking, the same LinUCB
model, the same slate policy and the same reward ledger, so a difference is
attributable to retrieval.

## 2. Unit of randomisation and exposure

* **Unit:** request (a `/recommendations` call for one user session), not user.
  Retrieval quality is a per-request property, and user-level randomisation would
  need weeks of exposure per user to accumulate enough requests.
* **Bucketing:** `sha256(test_salt + context_id) % 100`, 50/50. Deterministic given the
  context, so retries and duplicate deliveries land in the same arm. Log
  `test_salt` and the bucket with every request; without them the result is not
  auditable.
* **Consistency guard:** if a user's first request lands in arm B, later requests may
  land in arm A. That is acceptable for retrieval because nothing is learned per user
  at this layer — but it must be stated, because it forbids any per-user metric
  (e.g. "sessions per user") from being used as the primary metric.

## 3. Metrics

### 3.1 Primary metric

**Material open rate** = `open`/`inspect` events on recommended materials ÷
recommendation impressions, within 24 hours of the impression.

Why this and not NDCG: NDCG needs graded judgments we do not have at traffic scale.
Open rate is the first observed behaviour that retrieval can actually move — a
material that retrieval never returns cannot be opened.

Decision rule is on the **relative** lift with a two-proportion test at
α = 0.05 (two-sided), power = 0.80.

### 3.2 Secondary metrics (reported, not gating)

* click-through rate (clicks ÷ impressions);
* no-match rate (share of requests returning no candidates) — expect it to *rise*
  slightly, because the guard refuses off-topic queries that TF-IDF used to answer
  with something irrelevant;
* share of requests resolved at rank 1;
* p50/p95 retrieval latency;
* `free_to_paid_conversion` — **guardrail only** (§3.3), not a success metric.

### 3.3 Guardrails (any breach stops the test)

| guardrail | breach condition | rationale |
|---|---|---|
| p95 latency | > 300 ms for 30 consecutive minutes | the offline p95 is 18.7 ms on a smaller catalog; a 300 ms ceiling catches an indexing or memory regression |
| error rate | 5xx rate > 2× baseline | a new index build path can fail at load time |
| paid-content leakage | any paid material body appears in a public result | hard product/legal constraint |
| no-match rate | > baseline + 10 percentage points | the guard is over-refusing |
| free-to-paid conversion | > 5% relative drop, significant at α = 0.05 | retrieval that pushes free content can starve revenue |
| complaint rate ("not relevant") | > 2× baseline | the only direct signal that results feel wrong |

## 4. Sample size

Two-proportion test, α = 0.05 two-sided, power 0.80. `n` is per arm.

Open rate baseline and minimum detectable effect:

| baseline open rate | +5% rel | +10% rel | +20% rel |
|---|---|---|---|
| 5% | 122,100 | 31,200 | 8,200 |
| 10% | 57,800 | 14,700 | 3,800 |
| 15% | 36,300 | 9,300 | 2,400 |

Free-to-paid conversion, if anyone insists on gating on it:

| baseline conversion | +25% rel | +50% rel |
|---|---|---|
| 0.5% | 56,200 | 15,600 |
| 1.0% | 27,900 | 7,700 |
| 2.0% | 13,800 | 3,800 |

**Consequence:** conversion is not a practical primary metric. A realistic 1%
baseline with a 25% relative lift needs ≈28k impressions per arm, and purchases are
further throttled by the 24 h maturity window (`REWARD_MATURITY_SECONDS`) and by
`ALLOW_VERIFIED_PAYMENTS=false`, which means the purchase reward is currently dead
in production regardless of retrieval. Choose the open rate, and read conversion as a
guardrail.

**Assumption to verify before launch:** the baseline open rate is unknown here. Take
the real 14-day baseline from the events table and recompute `n` with the formula in
§8; do not reuse the table above blindly.

Alternative if traffic is low: a **switchback** design (alternate arms by 1-hour
block) reaches the same power with less calendar time but leaks time-of-day effects
into the comparison. Only use it if per-hour strata are analysed separately.

## 5. Duration

```
duration_days = ceil(n_per_arm * 2 / daily_matched_requests)
```

At 10k matching requests/day and a 10% relative MDE on a 10% baseline, that is
`ceil(29,400 / 10,000) = 3` days of exposure — but **run at least 7 days** to cover the
weekly cycle and to let the 24 h reward window mature for the last impressions. Cap
the test at 21 days; beyond that, seasonality drifts and the comparison decays.

Do not peek continuously. Pre-register **one** interim look at 50% of the planned
sample using an alpha-spending boundary (Pocock, α ≈ 0.029 per look is a workable
approximation); otherwise stop early only for guardrail breaches, not for a good
result.

## 6. Decision rule

| outcome | action |
|---|---|
| open rate lift significant and positive, no guardrail breach | enable `light-hybrid-search-v1` as the default retriever |
| lift positive but not significant after the planned sample | keep TF-IDF; report the effect size and its CI; do not ship on a null result |
| lift significant and negative | ship nothing; investigate with `scripts/monitor_drift.py` (channel and position slices) |
| no-match rate breach only | keep the retrieval channels, recalibrate the coverage guard on dev traffic; re-test |
| latency breach only | profile `lsa_retriever` and `light_hybrid._apply_synonyms`; the offline profile shows the fusion re-analysis of candidate evidence as the hot spot |
| conversion guardrail breach | do not ship the retrieval change as-is; add a paid-content floor to the slate, then re-test |

A null or negative result is a valid outcome and will be written into
`docs/boost_final_report.md` rather than reframed.

## 7. Instrumentation checklist

- [ ] log `test_salt`, `bucket`, `context_id`, `algorithm`, `status`, `candidates[].rank`
      on every retrieval call (the shape expected by `scripts/monitor_drift.py`);
- [ ] log `context_id`, `material_key`, `rank`, `channel` on every impression;
- [ ] log `kind` on every interaction, keeping `impression` distinct from positives;
- [ ] verify the 24 h reward window is applied consistently in both arms;
- [ ] snapshot the two arms' `state_digest` values at start and end (bandit drift would
      confound the comparison);
- [ ] run `scripts/monitor_drift.py` daily on both arms and keep the JSON output.

## 8. Formulas used

```
n_per_arm = ceil( (z_{1-alpha/2} + z_{1-beta})^2 * (p1(1-p1) + p2(1-p2)) / (p2 - p1)^2 )
p2        = p1 * (1 + relative_lift)
z_0.975   = 1.959964,  z_0.80 = 0.841621
```

Relative lift is computed against the control arm's observed rate, not against a
pre-registered guess.

## 9. Honest limits of this plan

* The offline evaluation shows a large gain on **paraphrase-style** queries, which were
  constructed to favour morphology-aware retrieval. Real traffic may contain far fewer
  of them, in which case the expected lift shrinks. The test is designed to detect a
  10% relative lift, not to confirm the offline +0.15 NDCG.
* Position bias inflates any CTR-like metric and is not corrected for. A/B on
  randomisation is still unbiased for the *difference*, provided both arms have the
  same slate presentation.
* The 24 h maturity window means the last day of impressions is incomplete at read-out.
  Either wait one extra day or drop the final day from both arms symmetrically.
* Nothing here replaces a real relevance judgment pass on the live catalog. The A/B
  test detects behavioural differences; it does not tell you whether the material was
  the *right* answer.
