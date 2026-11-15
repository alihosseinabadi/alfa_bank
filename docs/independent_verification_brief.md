# Independent verification brief — is `light-hybrid-search-v2` the best setup?

Hand this file to an independent agent (or a person) and ask it to **reproduce the
numbers first, then try to break the claim**. It is written so that a "no" is a valid
and useful answer.

Repo: `alfa_bank-ml`, branch `ml-boost`, head `4cb1d6a` (v2 is `02ecb80`).
Environment used here: Windows 11, Python 3.12.10, numpy 2.5.3, scipy 1.18.1,
scikit-learn 1.9.1, pandas 3.0.6, CPU only.

---

## 1. The claim under test

> Under the project constraints — no LLM calls, no transformer weights in the default
> path, CPU only, light dependencies — `light-hybrid-search-v2` is the best retrieval
> configuration we have measured, and it is better than `light-hybrid-search-v1` on
> paraphrased queries.

Two sub-claims, which should be judged separately:

1. **v2 > v1** on paraphrase NDCG@10, reproducibly on dev and frozen holdout.
2. **v2 is the best defensible choice**, i.e. it beats or ties every simpler
   alternative (`char_ngram`, `lsa`, `bm25_stem`, `tfidf`) on something that matters,
   without an unacceptable natural-query regression.

Sub-claim 2 is **not** claimed as proven. The current evidence says v2 ties
`char_ngram` on dev. Do not upgrade it to "beats" without new measurement.

---

## 2. Reproduce in five commands (repo root, PowerShell)

```powershell
$env:PYTHONUTF8=1

git log --oneline -3                         # expect head 4cb1d6a
python -m pytest backend/tests -q            # expect 275 passed, 47 skipped
python scripts/make_light_benchmark.py       # idempotent without --force
python scripts/evaluate_light_retrieval.py `
    --json data/synthetic/light_benchmark_v1/results_check.json
```

Then open `data/synthetic/light_benchmark_v1/results_check.json` and compare with
`results_light_v2.json`. The evaluator scores **all** engines in one run:
`tfidf`, `bm25`, `bm25_stem`, `char_ngram`, `lsa`, `light_hybrid` (v1),
`light_hybrid_v2`.

Notes:

- `PYTHONUTF8=1` is mandatory on Windows. Without it the suite raises ~78 cp1252
  `UnicodeDecodeError`s; that is pre-existing, not a regression.
- Do **not** run `make_light_benchmark.py --force`. Regenerating the benchmark
  invalidates every number below.
- `data/processed/catalog` does not exist in this checkout, so
  `scripts/build_light_index.py` cannot run. The v2 save/load round-trip is covered
  by `backend/tests/test_semantic_retrieval.py::test_v2_index_roundtrip`.
- 47 skips are environmental: 46 need `ALFA_EVENTS_TEST_DATABASE_URL`, 1 needs a
  missing optional artifact. They are not failures.

---

## 3. Frozen artifacts — verify before trusting any number

```powershell
(Get-FileHash data/synthetic/light_benchmark_v1/catalog.json -Algorithm SHA256).Hash.ToLower()
(Get-FileHash data/synthetic/light_benchmark_v1/queries.json  -Algorithm SHA256).Hash.ToLower()
```

Expected:

| file | sha256 |
|---|---|
| `catalog.json` | `f7957139a4b0bbcceac931d57b9a9780089a8fb132fbe9ea9925fdda9a941b64` |
| `queries.json` | `72e89bda7b55b102907bb06a2d289acde99d99b95468fcf0fc7ab548ed919a3c` |
| holdout digest | `8c9bacaa754a8dcafbf1dbe77678f53061ce09f86b5cc2138150a6972cf7bb85` |

Shape: 168 materials, 294 chunks, 14 topics, 104 cases (73 dev / 31 holdout;
59 dev and 25 holdout relevance cases). If any hash differs, stop: the comparison is
not valid.

---

## 4. Claimed numbers to reproduce

Paraphrase NDCG@10, the metric the claim rests on:

| split | v1 | v2 | paired Δ [95% CI] | W/L/T |
|---|---|---|---|---|
| dev (34) | 0.434 | 0.478 | +0.031 [+0.014, +0.049] | 29/7/23 |
| holdout (8) | 0.418 | 0.463 | +0.028 [+0.009, +0.050] | 11/3/11 |

Secondary:

| metric | dev | holdout |
|---|---|---|
| natural NDCG@10 v1 → v2 | 0.805 → 0.818 | 0.824 → 0.844 |
| paraphrase top-1 v1 → v2 | 0.294 → 0.412 | 0.500 → 0.500 |
| paraphrase Success@5 v1 → v2 | 0.676 → 0.735 | 0.625 → 0.625 |
| v2 − `char_ngram` NDCG@10 | −0.002 [−0.039, +0.032] | +0.023 [−0.035, +0.092] |
| v2 − `tfidf` NDCG@10 | +0.190 [+0.121, +0.261] | +0.144 [+0.041, +0.257] |
| v2 latency p50 / p95, ms | 15.55 / 18.96 | 8.12 / 12.76 |
| constraint violations | 0 of 3 cases | 0 of 5 cases |
| off-topic refusal | 1.000 | 1.000 |

Bootstrap is paired, 2,000 rounds, seed 7, implemented in
`scripts/evaluate_light_retrieval.py`.

---

## 5. Decision rule

Accept sub-claim 1 if and only if:

- the holdout paraphrase Δ is positive and its paired 95% CI excludes 0;
- natural NDCG@10 does not fall by more than 0.02 on either split;
- constraint violations stay 0 and off-topic refusal stays 1.000.

Accept sub-claim 2 ("best defensible") only if, in addition:

- v2 beats `char_ngram` on holdout with a CI excluding 0, **or** the report states
  plainly that the two tie and prefers v2 for a stated non-NDCG reason;
- no simpler engine matches v2 on both splits.

If either fails, say so. The report already says `char_ngram` ties v2 on dev; a
finding that it also ties on holdout is consistent with the current text, not a
contradiction.

---

## 6. Try to break it — five concrete hypotheses

Run each on **dev only**; touch the holdout once, at the end, for the chosen
configuration. That is the rule the original work followed.

| id | hypothesis | how |
|---|---|---|
| H1 | `char_ngram` alone is as good and 6× faster, so the fused path is not worth it | compare per-case deltas and latency; decide on operational grounds |
| H2 | a different component count (20 or 60) beats 40 | `LightRetrievalPolicyV2(semantic_components=…)` on dev |
| H3 | the semantic channel adds nothing over v1 | `light_hybrid` vs `light_hybrid_v2`, paired CI |
| H4 | the gain is a few cases, not a distribution shift | inspect per-case NDCG deltas; a 29/7/23 split should not be one outlier |
| H5 | the latency claim is machine-specific | rerun; absolute ms varied run to run here (v1 holdout 7.69 vs dev 14.72) |

Also worth checking: does the v2 gain survive if you drop the synonym expansion
(`semantic_synonym_weight=0`)? If yes, the gain is the material-level LSA, not the
dictionary. If no, the dictionary is doing the work and should be documented as such.

---

## 7. Known caveats — do not rediscover these the hard way

1. **Relevance is construction-derived**, not human-judged. The benchmark is a
   regression harness. It cannot establish production relevance.
2. **Holdout paraphrase n = 8.** One case moves the mean by 0.125. Wide CIs are
   expected, not a bug.
3. **~30 dev configurations were tried** before freezing. Dev is partly overfit;
   holdout is the only clean read, and it was read once.
4. **v2 trades natural quality for paraphrase quality.** Two natural queries lose
   NDCG: `что можно автоматизировать в рутине для онлайн-школы` (−0.147) and
   `что такое ltv и cac для небольшого кафе` (−0.138).
5. **v2 is slower than the incumbent**: 15.55 vs 8.13 ms p50 on dev, on a catalogue
   8.6× smaller than production.
6. **E5 is unmeasured.** No weights, no vectors. Nothing in the default path uses it.
7. **The real catalogue is absent** (`data/raw`, `data/interim`, `data/processed`,
   `reports`, `artifacts`), so no real-catalog evaluation is possible here.
8. **One false refusal persists**: `как улучшить оценки магазина` is refused because
   the OOD guard is unchanged in both versions.

---

## 8. Files to read, in this order

| file | why |
|---|---|
| `docs/semantic_search_v2.md` | the v2 design, dev exploration log, holdout result, failure analysis, 4/10 rating |
| `docs/light_search_evaluation.md` | v1 tables and failure analysis |
| `docs/boost_final_report.md` §2, §5, §8 | consolidated before/after and the claims ledger |
| `backend/app/ml/semantic_retriever.py` | the new channel (~200 lines) |
| `backend/app/ml/light_hybrid.py` | v1 refactored into hooks, `LightHybridRetrieverV2` subclass |
| `backend/app/data_preparation/light_index.py` | version registry and save/load |
| `scripts/evaluate_light_retrieval.py` | the harness and pairwise bootstrap |
| `backend/tests/test_semantic_retrieval.py` | 18 behavioural tests |
| `data/synthetic/light_benchmark_v1/results_light_v2.json` | raw numbers |

---

## 9. What to report back

Use this shape, so results are comparable:

```
PASS/FAIL  v2 > v1 on dev        (measured Δ, CI)
PASS/FAIL  v2 > v1 on holdout    (measured Δ, CI)
PASS/FAIL  no natural regression (measured Δ)
PASS/FAIL  constraints + refusal
VERDICT    best defensible setup: yes / no / tie-with-char_ngram
NOTES      anything that contradicted docs/semantic_search_v2.md
```

If a number differs from §4 by more than bootstrap noise, say which command produced
it and whether the benchmark hashes still match.
