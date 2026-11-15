# Alfa-Kurs ML boost — final report

Date: 2026-11-15. Branch `ml-boost`, base `90f6bcd` (`ml`), head `96e14d6`.
Environment: Windows 11, Python 3.12.10, numpy 2.5.3 / scipy 1.18.1 / scikit-learn 1.9.1,
CPU only, no LLM calls, no transformer weights present.

This report separates three things on purpose:

1. **measured here**, with the command that produced it;
2. **not measured**, and why;
3. **decided, not measured** — defaults and judgement calls that the numbers cannot
   justify.

Every retrieval number below comes from a **public synthetic benchmark** with
construction-derived relevance. It is a regression harness. It is not evidence of
production relevance, and no number here should be quoted to a stakeholder without
that sentence attached.

---

## 1. What was delivered

| commit | scope | files |
|---|---|---|
| `5f9b084` | Phase 0: environment, test baseline, config drift, LF normalization | `.gitattributes`, `.env.example`, `backend/requirements.txt` |
| `de97666` | Phase 1: stemmed light hybrid, additive and versioned | `ru_normalize.py`, `synonyms.py`, `ngram_retriever.py`, `lsa_retriever.py`, `light_hybrid.py`, `light_index.py`, `retrieval_contracts.py`, `bm25_ru_stem.py`, 2 scripts, 20 tests |
| `2b6d6b5` | Phase 1 evaluation: benchmark, harness, docs | `make_light_benchmark.py`, `evaluate_light_retrieval.py`, `docs/boost_baseline.md`, `docs/light_search_evaluation.md`, `docs/evaluation_methodology.md` §12 |
| `a9d2be8` | Phase 5.1: LinUCB batch scoring | `linucb.py`, `ucb_ranking.py`, `benchmark_linucb.py`, `docs/linucb_optimization.md`, 7 tests |
| `1eaf030` | Phase 2/6: agreement + drift tooling, A/B plan | `judgment_agreement.py`, `monitor_drift.py`, `docs/ab_test_plan.md`, 9 tests |
| `96e14d6` | Phase 4.1: onboarding layer | `onboarding.py`, `data/onboarding_goal_topics.json`, `docs/onboarding.md`, 24 tests |

New runtime behaviour is **off by default**. The production path
(`tfidf-search-v1`) is byte-identical in behaviour; the light path is a separate
version string and a separate policy, reachable through `--engine light`. The
onboarding module is not wired to any route. No existing test was modified to make a
new one pass.

Test suite: **189 passed / 5 failed / 3 errors** at the start → **257 passed, 47
skipped** at the end. The 47 skips are unchanged environment gaps (46 need
`ALFA_EVENTS_TEST_DATABASE_URL`; 1 needs a missing optional artifact).

Added dependencies: `snowballstemmer>=2.2,<3.0` (required by code that already
imported it and was missing from `backend/requirements.txt`). Nothing else. E5 remains
optional and unused.

---

## 2. Retrieval — measured before and after

Command (repo root):

```powershell
$env:PYTHONUTF8=1; python scripts/make_light_benchmark.py
$env:PYTHONUTF8=1; python scripts/evaluate_light_retrieval.py `
    --json data/synthetic/light_benchmark_v1/results_light_v1.json
```

Benchmark: 168 materials / 294 chunks / 14 topics, 104 cases (84 relevance, 12
off-topic, 8 constraint), frozen split 73 dev / 31 holdout. Hashes in
`docs/boost_baseline.md` §5; any change invalidates these numbers.

### 2.1 NDCG@10, dev (59 relevance cases) and holdout (25)

| engine | dev natural | dev paraphrase | holdout natural | holdout paraphrase |
|---|---|---|---|---|
| `tfidf` (production, before) | 0.634 | 0.284 | 0.721 | 0.274 |
| `bm25` (before) | 0.601 | 0.207 | 0.626 | 0.174 |
| `bm25_stem` (ablation) | 0.753 | 0.379 | 0.793 | 0.417 |
| `char_ngram` (ablation) | 0.825 | 0.477 | **0.866** | 0.344 |
| `lsa` (ablation) | 0.789 | 0.459 | 0.807 | **0.488** |
| **`light_hybrid` (after)** | **0.805** | **0.434** | 0.824 | 0.418 |

Paired differences over the same cases (bootstrap 2000 rounds, seed 7):

| comparison | dev Δ NDCG@10 [95% CI] | holdout Δ NDCG@10 [95% CI] | verdict |
|---|---|---|---|
| hybrid − tfidf | +0.159 [+0.087, +0.232] | +0.116 [+0.012, +0.227] | **measured win on both splits** |
| hybrid − bm25 | +0.218 [+0.149, +0.290] | +0.213 [+0.127, +0.309] | **measured win on both splits** |
| hybrid − bm25_stem | +0.054 [+0.020, +0.091] | +0.021 [−0.001, +0.044] | small win on dev, tie-ish on holdout |
| hybrid − char_ngram | −0.033 [−0.073, +0.003] | −0.005 [−0.056, +0.056] | **no win; a tie at best** |
| hybrid − lsa | −0.008 [−0.047, +0.026] | −0.011 [−0.061, +0.036] | **no win** |

What this supports: the fused path is **materially better than the shipped TF-IDF**
and better than lexical BM25, by +0.12…+0.22 NDCG@10, reproducibly on dev and holdout.
Paraphrase NDCG roughly doubles (0.28 → 0.43), which is the morphology effect the
stemmed channel was built for.

What this does **not** support: that the fusion is better than its best single
channel. `char_ngram` alone matches or beats it on NDCG@10; `lsa` matches it. The
fusion is kept for robustness and for the refusal guard (§2.4), not for ranking
quality.

### 2.2 Success@5 and Recall@50

Success@5 natural: 0.840 (tfidf) → **1.000** (hybrid), same on holdout (0.941 →
1.000). Paraphrase Success@5: 0.441 → **0.676** dev, 0.375 → 0.625 holdout. Pooled
Recall@50 is 1.000 for every stemmed/fused engine on natural queries, so the remaining
gap is ranking, not candidate generation, for that family.

### 2.3 Latency

Warm, per query, `k=50`, 168 materials:

| engine | p50 ms | p95 ms |
|---|---|---|
| bm25 | 0.35 | 0.98 |
| bm25_stem | 0.86 | 1.55 |
| char_ngram | 2.69 | 3.64 |
| lsa | 2.70 | 3.48 |
| tfidf (production) | 8.81 | 10.54 |
| **light_hybrid** | **14.94** | **18.69** (dev) / 17.03 (holdout) |

The hybrid is **1.7× slower than the incumbent** and slower than every individual
channel. The `<100 ms` target is met **only at this catalogue size**: production is
≈8.6× larger in materials and ≈34× in chunks, and per-query cost grows with catalogue
size. "18 ms in production" is not a measured claim.

### 2.4 Refusal, constraints, false refusals

* Off-topic refusal, dev (9 cases): tfidf 1.000, bm25 1.000, bm25_stem 1.000,
  lsa 1.000, **char_ngram 0.818**, hybrid 1.000. Holdout (3 cases) all 1.000 —
  uninterpretable at n=3.
* The guard therefore **restores the incumbent's behaviour**; it does not improve on
  it. Its value is that shipping `char_ngram` alone would regress refusal, so the
  fusion is the price of using char n-grams at all.
* Constraint violations: **0** for all six engines. (The first run reported 119; that
  was an evaluator bug — constraints were nested instead of top-level, so they were
  ignored. Fixed before the tables above were recorded. The invalid run is not quoted
  anywhere.)
* One observed false refusal: `как улучшить оценки магазина` →
  `insufficient_query_coverage`, because `магазин` is indexed only inside the
  hyphenated token `интернет-магазине`. 1 of 34 dev paraphrase cases. This is the
  visible cost of the guard.

### 2.5 What did not help

| tried | result |
|---|---|
| fusing three channels | ties the best single channel (`char_ngram`) on NDCG@10; does not beat it |
| the hybrid as a latency win | it is **slower** than every channel it combines |
| the coverage guard as a refusal improvement | refusal was already 1.000 for the incumbent; the guard only prevents a regression |
| hand-set fusion weights | not tuned; a dev sweep on 59 cases would mostly fit noise (see §6) |
| LSA as a semantic fix | +0.01…+0.08 NDCG over `bm25_stem` at best; does not solve zero-overlap paraphrases (§2.6) |

### 2.6 Failure analysis that remains true after the change

Paraphrases with no shared vocabulary still fail for every engine in the default path:

| query | target | returned top-1 |
|---|---|---|
| `где искать клиентов для бизнеса` | Каналы привлечения | Кредит для бизнеса |
| `что говорить клиенту по телефону` | Скрипты звонков | Удержание покупателей |
| `как работать по усн` | Упрощённая система | НДС |
| `как убрать ручную работу из процессов` | Автоматизация рутины | Работа с жалобами |

These need semantics. Stemming, char n-grams and a 120-component LSA over 168
documents are not semantics. The +0.15 NDCG does not fix them, and the report should
never imply it does.

---

## 3. Bandit / ranking — measured before and after

### 3.1 LinUCB scoring (Phase 5.1)

`SharedLinUCB.score()` validated the whole 45×45 state on every candidate (Cholesky +
`np.linalg.cond`) and solved the system twice. Now validation and the inverse are
computed **once per state**, guarded by `state_digest()`, and candidates are scored as
a batch.

```powershell
$env:PYTHONUTF8=1; python scripts/benchmark_linucb.py --json data/synthetic/linucb_benchmark_v1.json
```

| path | p50 ms | p95 ms | mean ms |
|---|---|---|---|
| before | **30.50** | 35.05 | 31.36 |
| after | **1.10** | 1.63 | 1.19 |
| speedup | **27.8×** | 21.5× | 26.4× |

Equivalence: max absolute score difference **1.11e-16** on 50 candidates after 10
`observe` + 1 `revise`; `state_digest()` is byte-identical, and a direct asymmetric
mutation still raises. Not measured: end-to-end request latency (no service running
here) and `validate_features` cost (still per candidate).

### 3.2 Simulator numbers — unchanged, and still unflattering

These are self-contained simulations with fixed seeds, reproducible here:

| policy | stage-8 total reward | stage-9 total reward |
|---|---|---|
| `prior` | 35.4 | 68.2 |
| `greedy` | 52.6 | — |
| `linucb` | 50.8 | — |
| `ucb` | — | 107.1 |
| `slate` (epsilon-diverse) | — | 51.8 |

Nothing in this work improved these, and the speed-up does not change ranking
decisions. Two findings stand and should not be buried:

* `linucb` does **not** beat plain `greedy` in the stage-8 simulation (50.8 vs 52.6);
* the tuned epsilon-diverse slate policy is far **worse** than plain `ucb`
  (51.8 vs 107.1).

Also from code: the practical reward ceiling is 0.15 because
`allow_verified_payments` is never set to `true`, so the 1.0 purchase reward is dead.
Saturation in the ledger would reflect a switch nobody turns on.

---

## 4. New tooling, and what it can/cannot say here

| tool | measures | status in this repo |
|---|---|---|
| `scripts/judgment_agreement.py` | Cohen's κ, quadratic-weighted κ, coverage, undefined-κ handling between two assessors | implemented + 5 tests; **cannot be applied** — `retrieval_cases_v2.json` has 100 queries and **no grades** |
| `scripts/monitor_drift.py` | no-match rate, vocabulary coverage, CTR by position and channel | implemented + 4 tests; needs a live event store |
| `docs/ab_test_plan.md` | request-level 50/50 design, primary metric, guardrails, stopping rule | **proposal only**; nothing has run on real traffic |
| `backend/app/ml/onboarding.py` | six answers → existing profile fields, history rule, starter picks | implemented + 24 tests; **not wired to any route or UI** |

The onboarding evidence is behavioural, not product evidence: no completion rate, no
drop-off, no effect on first-session clicks. Its starter set also gets sparse under
`free_only` + 15 min (2–4 cards of 6). Details and limits: `docs/onboarding.md`.

---

## 5. Claims ledger

| claim | status | evidence |
|---|---|---|
| light hybrid beats shipped TF-IDF on NDCG@10 | **measured** | paired Δ +0.159 dev, +0.116 holdout, CIs exclude 0 |
| light hybrid beats lexical BM25 | **measured** | paired Δ +0.218 / +0.213 |
| word-form robustness | **measured, channel-scoped** | exact ordering invariant on the stemmed channel; top-3 only for the fused path |
| precise no-match for out-of-domain queries | **measured for zero-overlap queries** | 12 synthetic cases, `no_eligible` + `query_out_of_domain` |
| the lunar-landing production failure is fixed | **not demonstrated** | the real index and query set are absent; only the zero-overlap case is reproducible |
| refusal rate improves | **not met; premise false here** | incumbent already 1.000 |
| E5 or E5-hybrid value | **unmeasured** | no weights, no vectors; nothing in the default path uses E5 |
| production latency under 100 ms | **unverified** | 18.69 ms p95 on a catalogue 8.6× smaller than production |
| LinUCB scoring 27.8× faster | **measured**, scores match | 30.50 → 1.10 ms p50, max diff 1.11e-16 |
| bandit policy quality improved | **no change** | simulator numbers identical to baseline |
| two-annotator agreement | **not measurable** | no human grades in the repository |
| onboarding improves cold-start outcomes | **not measured** | module not deployed; no events |

---

## 6. Decisions that are judgment, not measurement

Stated so they are not mistaken for findings:

* **Fusion weights were not tuned.** `bm25_stem 1.0`, `char_ngram 0.8`, `lsa 0.6`,
  RRF `k=60`. A dev-only sweep might close the 0.033 gap to `char_ngram`, but with 59
  dev cases the expected gain is inside the noise band; the acceptance criterion was
  already met. If someone tunes them later: dev only, configuration written down
  before the holdout is read, number of configurations reported.
* **The guard thresholds (coverage < 0.3, zero coverage) were not tuned.** They are
  round numbers chosen to separate "no vocabulary" from "partial vocabulary". The
  `магазин` false refusal is the known price.
* **Synonym expansion is boost-only and evidence-scoped.** An expansion term must
  appear in the candidate's own evidence chunk, so a synonym cannot invent relevance.
  This was a design choice to keep the public index honest; it is not measured as
  better than unrestricted expansion.
* **Onboarding goals→topics is a hand-written hypothesis** (8 goals × 2 topics),
  never validated against user language.
* **Onboarding stops acting after 3 interactions.** A questionnaire answer should not
  outrank observed behaviour; 3 is a policy default, not a fitted value.

---

## 7. Not done, and why

| pending work | blocker |
|---|---|
| Phase 2 remainder (judged-set construction checks) | no human judgments exist; anything built on them would be fabricated |
| Phase 3 | not started; depends on judged data for anything beyond the synthetic harness |
| Phase 4.2 / 4.3 (personalised cold-start, onboarding API/events) | needs a route and an event; `event_service.py` was out of scope |
| Phase 5.2–5.5 (`tick()` incremental update, `load_checkpoint()` without replay) | DB-backed stages 7–9 cannot run here (no Postgres/Docker); 46 of 47 skips are that |
| real-catalogue retrieval metrics | private catalog, indexes and judgments absent (`data/processed`, `reports`, `artifacts` all missing) |
| E5 and E5-hybrid evaluation | no weights, no vectors |
| live A/B | no traffic, no service |

Also unfixed, pre-existing, and documented: on Windows without `PYTHONUTF8=1` the
suite produces ~78 cp1252 `UnicodeDecodeError`s. Test files were not modified.

---

## 8. Recommendation

1. **Do not ship the light path on the strength of these numbers alone.** They justify
   an A/B test, not a rollout: relevance labels are synthetic, and production latency
   is unverified at 8.6× the catalogue size.
2. **Ship the LinUCB batch change if the ranking code is touched at all.** It is
   score-equivalent to 1e-16, keeps provenance digests identical, and removes a 27.8×
   cost from every slate. It is the one change here whose benefit does not depend on
   unmeasured quality.
3. **Run the A/B test first on retrieval only**, with the bandit held fixed
   (`docs/ab_test_plan.md`), and treat `char_ngram` as the honest competitor — the
   fusion must beat it on something that matters (refusal, latency, tail behaviour) or
   the simpler channel is the better ship.
4. **Do not quote "NDCG 0.63 → 0.81"** as a production improvement. Correct phrasing:
   "on a 104-case synthetic benchmark with construction-derived labels, the fused path
   beats the shipped TF-IDF by 0.12–0.16 NDCG@10 on held-out cases; relevance on real
   traffic is unmeasured."
5. **Before any onboarding work continues**, emit an onboarding-completion event.
   Without a denominator, no onboarding change can be evaluated.

---

## 9. Reproduction

```powershell
# from the repository root
$env:PYTHONUTF8=1

python -m pytest backend/tests -q                       # 257 passed, 47 skipped
python scripts/make_light_benchmark.py                  # idempotent without --force
python scripts/evaluate_light_retrieval.py `
    --json data/synthetic/light_benchmark_v1/results_light_v1.json
python scripts/benchmark_linucb.py --json data/synthetic/linucb_benchmark_v1.json
python scripts/simulate_linucb_stage8.py
python scripts/simulate_slate_stage9.py
```

Companion documents: `docs/boost_baseline.md` (what could not be measured),
`docs/light_search_evaluation.md` (full retrieval tables and failure analysis),
`docs/evaluation_methodology.md` §12 (harness validity), `docs/linucb_optimization.md`,
`docs/ab_test_plan.md`, `docs/onboarding.md`.
