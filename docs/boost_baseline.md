# Boost baseline — what was actually measured before changing anything

Status: Phase 0 record. Written 2026-11-15 on branch `ml-boost`.

This file separates three very different things that are easy to confuse:

1. **Measured here** — numbers produced in this repository, with the exact command.
2. **Not reproducible here** — numbers the project documents claim, but whose inputs
   (private catalog, indexes, judgments) are absent, so they cannot be re-run.
3. **Configuration drift** — places where the template, requirements and code
   disagreed, and what was done about it.

Read section 4 before quoting any number from `docs/quality_stage56.md`.

---

## 1. Environment

| item | value |
|---|---|
| OS | Windows 11 (10.0.22631), not Linux — see the encoding note in §2 |
| Python | 3.12.10 |
| numpy / scipy / scikit-learn | 2.5.3 / 1.18.1 / 1.9.1 |
| snowballstemmer | installed (`>=2.2,<3.0`, added to `requirements.txt` in this phase) |
| pymorphy3 | **not installed** — the lemmatizer path is untested in this environment |
| git | repository was **not** a git repo at start; initialized, baseline snapshot committed as `90f6bcd` on branch `ml` |

Working branch for all of this work: `ml-boost`, created from `ml` at `90f6bcd`.

---

## 2. Test suite baseline

Command (from the repository root — running it from `backend/` breaks
`test_audit_judgments_stage10.py`, which imports `scripts`):

```powershell
$env:PYTHONUTF8=1; python -m pytest backend/tests -q
```

| run | result | cause |
|---|---|---|
| first run, before any change | **189 passed, 47 skipped, 5 failed, 3 errors** | see below |
| after Phase 0 fixes | **197 passed, 47 skipped** | two dependency/IO problems fixed, seven new tests not yet added |
| after Phase 1 | **217 passed, 47 skipped** | +20 behavioural tests for the light path |

The original failures had three concrete causes, all environmental rather than
logical:

1. `snowballstemmer` was imported by `backend/app/ml/bm25_ru_stem.py` but missing
   from `backend/requirements.txt` (it was only in `requirements-catalog.txt`).
   That produced 2 collection errors.
2. Six tests shell out to `git rev-parse HEAD`. The directory was not a git
   repository, so they failed. Initialising the repository fixed them.
3. 78 `UnicodeDecodeError`s on cp1252 when reading UTF-8 fixtures. Those tests
   assume a UTF-8 locale (Linux/WSL). `PYTHONUTF8=1` fixes them; the underlying
   tests were **not** changed. **Without `PYTHONUTF8=1` the suite still reports
   ~78 encoding errors** — that is a pre-existing portability bug, out of scope
   here, and it is not a regression.

47 tests are skipped in this environment. 46 of them require
`ALFA_EVENTS_TEST_DATABASE_URL` (Postgres, stages 7–9 of the project); there is no
Docker or Postgres available here, so **the database-backed pipeline is untested**
in this work. One skip is a missing optional artifact.

---

## 3. What cannot be measured here at all

The repository contains the *code* of the evaluation harness but none of its
*inputs*. Verified absent:

| path | needed by | status |
|---|---|---|
| `data/processed/catalog` (≈1,444 materials, ≈9,965 chunks) | `scripts/build_retrieval_index.py`, all retrieval evaluation | **missing** |
| `data/interim`, `data/raw` | corpus building | **missing** |
| `reports/`, `artifacts/` | stage-5/6 analysis, saved indexes, E5 vectors | **missing** |
| `data/courses/courses.csv` | tiny public sample | present, **12 data rows** |
| E5 weights (`E5_MODEL_DIR`) | E5 channel | **missing** |

Consequences, stated plainly:

* `scripts/evaluate_retrieval.py`, `scripts/evaluate_stage56.py` and
  `scripts/analyze_stage56.py` **cannot run** here. They need the private bundles.
* The **E5 and hybrid results are unmeasured** in this work. Not "unchanged", not
  "assumed equal" — unmeasured.
* `data/synthetic/retrieval_cases_v2.json` has 100 queries but **no relevance
  grades**, so no NDCG can be computed from it. `judged_metrics` correctly raises
  on unjudged top-k.
* Every NDCG-style number below therefore comes from a **new public synthetic
  benchmark** whose labels are construction-derived, not human-judged. It is a
  regression harness, not production quality.

---

## 4. Author-reported numbers — **unverified in this repository**

`docs/quality_stage56.md` and `docs/retrieval_stage5_status.md` report the
following. I could not re-run any of it (missing inputs, §3). Treat these as
claims inherited from the original authors:

| claim | source | why it cannot be checked here |
|---|---|---|
| TF-IDF returns 16 business materials for a lunar-landing query, 8 for chemical-element synthesis | `docs/quality_stage56.md` | needs the real index and the real query set |
| test06 (customer-service podcast) is missed because of word forms | `docs/quality_stage56.md` | needs the real catalog |
| BM25 answers `needs_clarification` where `no_eligible` is correct | `docs/quality_stage56.md` | needs the real query set |
| prior ranking changed the top result 0 times in 21 tasks; NDCG gain ≈ +0.001 | `docs/quality_stage56.md` | needs the 21 judged scenarios |
| judged set = 21 relevance + 7 check scenarios, one AI annotator | `docs/evaluation_methodology.md` | judgments themselves are private |

The stage-8/stage-9 bandit numbers **are** reproducible here, because those
scripts are self-contained simulations with fixed seeds:

```powershell
$env:PYTHONUTF8=1; python scripts/simulate_linucb_stage8.py
$env:PYTHONUTF8=1; python scripts/simulate_slate_stage9.py
```

Deterministic output recorded for reference (total reward):

| policy | stage-8 reward | stage-9 reward |
|---|---|---|
| `prior` | 35.4 | 68.2 |
| `greedy` | 52.6 | — |
| `linucb` | 50.8 | — |
| `ucb` | — | 107.1 |
| `slate` (epsilon-diverse) | — | 51.8 |

Two findings worth carrying forward, both visible without any private data:

* `linucb` does **not** beat plain `greedy` in this simulation (50.8 vs 52.6).
* the epsilon-diverse slate policy as tuned is far **worse** than plain `ucb`
  (51.8 vs 107.1). That is a real signal, not a rounding artefact.

Also verifiable from code: the reward ceiling is 0.15 in practice, because
`allow_verified_payments` is never set to `true` anywhere in the codebase, so the
purchase reward (1.0) is dead. Any saturation in the ledger therefore reflects a
switch nobody turns on.

---

## 5. Reproducible baseline: the public synthetic benchmark

Created in Phase 1 (`scripts/make_light_benchmark.py`) precisely because §3 leaves
no runnable benchmark. 168 synthetic materials / 294 chunks / 14 topics, 104
cases: 84 relevance, 12 off-topic refusal, 8 constraint cases. Split: 73 dev / 31
holdout, frozen by case-id hash before any measurement.

Hashes (record these; any change invalidates the tables):

| file | sha256 |
|---|---|
| `catalog.json` | `f7957139a4b0bbcceac931d57b9a9780089a8fb132fbe9ea9925fdda9a941b64` |
| `queries.json` | `72e89bda7b55b102907bb06a2d289acde99d99b95468fcf0fc7ab548ed919a3c` |
| holdout case-id digest | `8c9bacaa754a8dcafbf1dbe77678f53061ce09f86b5cc2138150a6972cf7bb85` |

Baseline engines on that benchmark (the "before" for Phase 1):

| split | engine | NDCG@10 natural | NDCG@10 paraphrase | Success@5 natural | Success@5 paraphrase | p50 / p95 ms |
|---|---|---|---|---|---|---|
| dev | `tfidf` (production) | 0.634 | 0.284 | 0.840 | 0.441 | 8.81 / 10.54 |
| dev | `bm25` | 0.601 | 0.207 | 0.840 | 0.353 | 0.35 / 0.98 |
| holdout | `tfidf` (production) | 0.721 | 0.274 | 0.941 | 0.375 | 8.19 / 9.36 |
| holdout | `bm25` | 0.626 | 0.174 | 0.941 | 0.375 | 0.39 / 0.83 |

Full tables, CIs and paired differences: `docs/light_search_evaluation.md`.

**Interpretation limit.** These are synthetic relevance labels. The paraphrase
family is deliberately built from wordings that avoid the indexed forms, so it is
a morphology stress test, not a sample of real user queries. Use these numbers to
detect regressions; never present them as production quality.

**Caveat on how this baseline was produced.** The generator was corrected twice
before the tables above were recorded (a junk `ue1`-style tag, and an aspect phrase
that was identical in every query, making it useless as a discriminator). Numbers
from those dry runs are not reported anywhere. The benchmark has been re-run since
the latest generator change, and no retrieval parameter has been changed after
that run.

---

## 6. Configuration drift (Phase 0b)

The brief listed a drift between `.env.example` and the code. Verified in source:

| setting | template said | code does | resolution |
|---|---|---|---|
| `LINUCB_RIDGE` | `0.01` | `1.0` (`learning_service.py`) | template changed to 1.0 |
| `LINUCB_ALPHA` | not clearly pinned | `0.5` | template documents 0.5 |
| `REWARD_PURCHASE` | `10` | `1.0` (`reward_policy.py`, bounded in [0,1]) | template changed to 1.0 |
| `REWARD_CLICK` / `REWARD_INSPECT` | ambiguous | `0.1` / `0.15` | template documents both |
| `REWARD_MATURITY_SECONDS` | ambiguous | `86400` | template documents it |
| `EMBEDDING_MODEL` | a MiniLM id | `intfloat/multilingual-e5-base` | template changed to E5 |
| `FEATURE_VERSION` | absent | `pair-features-v1` | template documents it |
| `snowballstemmer` | missing | imported by `bm25_ru_stem.py` | added `snowballstemmer>=2.2,<3.0` |

**The code was not changed to match the template.** The template was changed to
match the code, because the code values are the ones that produced every existing
number. Changing `LINUCB_RIDGE` to 0.01 would silently alter bandit behaviour and
invalidate prior comparisons.

`.env.example` now also states, per value, which source file is authoritative.

---

## 7. Line endings (Phase 0c)

`.gitattributes` added (`* text=auto eol=lf`). Nine files in
`backend/app/ml/` and `backend/app/services/` had a mixed CRLF/LF body
(`linucb.py`, `ucb_ranking.py`, `slate_policy.py`, `reward_policy.py`,
`offpolicy_stage9.py`, `learning_service.py`, `learning_checkpoint.py`,
`recommendation_orchestrator.py`, `learning_ranking.py`). They were normalized to
LF with **no textual change**: the diff is line endings only, and the full test
suite stayed green (197 passed) immediately after.

---

## 8. Gaps that remain open at the end of Phase 0

| gap | status |
|---|---|
| real-catalog retrieval metrics | impossible here (no catalog/index) |
| E5 and E5-hybrid value | **unmeasured** (no weights, no vectors) |
| stages 7–9 database behaviour | untested (no Postgres) |
| 21-scenario judged set | absent; replaced by a 104-case synthetic set with construction-derived labels |
| two-annotator agreement | no judgments exist at all, so kappa is unmeasurable in this environment |
| `PYTHONUTF8` requirement on Windows | pre-existing, unfixed, documented |
