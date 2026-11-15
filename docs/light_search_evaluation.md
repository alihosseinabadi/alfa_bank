# Light search evaluation — Phase 1

Date: 2026-11-15. Branch `ml-boost`. Retrieval policy: `light-hybrid-search-v1`.

This document reports **only what was run in this repository**. The real
Alfa-Kurs catalog, the judged scenarios and the E5 vectors are not present here, so
every number below comes from a public synthetic benchmark whose relevance is
construction-derived. It is a regression harness, not a measurement of production
relevance. Section 8 lists what it cannot tell you.

> **Later addition:** a v2 path (`light-hybrid-search-v2`) with a material-level
> semantic channel is evaluated separately in `docs/semantic_search_v2.md`. Every
> number in *this* document is v1 and remains valid; v2 raises dev paraphrase
> NDCG@10 from 0.434 to 0.478 and holdout from 0.418 to 0.463.

Summary of the honest result:

* The light hybrid clearly beats the **currently shipped TF-IDF** and both BM25
  variants on NDCG@10 and Success@5, on dev and on the frozen holdout.
* It does **not** beat the single strongest channel (char n-grams) on NDCG@10. It
  ties it. The fused score buys robustness, not extra ranking quality.
* It does **not** improve the refusal rate over the incumbent, because the
  incumbent already refuses every off-topic query in this benchmark. The guard
  preserves the incumbent's behaviour; it does not beat it.
* Word-form robustness is real and measured. Out-of-domain rejection is real and
  measured — but only for queries with zero catalog vocabulary.

---

## 1. What was added

| file | role |
|---|---|
| `backend/app/ml/ru_normalize.py` | Snowball stemming (pymorphy3 when installed), cached, Latin/digit tokens untouched |
| `backend/app/ml/ngram_retriever.py` | char_wb 3–5-gram TF-IDF channel, material max pooling |
| `backend/app/ml/lsa_retriever.py` | TruncatedSVD (120 comps, `random_state=0`) over stemmed TF-IDF |
| `backend/app/ml/synonyms.py` + `data/synonyms_ru.json` | curated canonicalization + boost-only expansion |
| `backend/app/ml/light_hybrid.py` | RRF fusion, OOD guard, refusal semantics |
| `backend/app/data_preparation/light_index.py` | save/load by deterministic refit + identity verification |
| `scripts/build_light_index.py`, `scripts/search_materials.py --engine light` | build and query the new path |
| `backend/tests/test_light_retrieval.py` | 20 behavioural tests |

Additive by construction: `tfidf-search-v1`, its index format and its policy are
untouched; `RetrievalPolicy` is unchanged; the new path has its own version string
and its own policy class. `RussianStemBM25Retriever` gained an optional `analyzer`
hook whose default reproduces the old behaviour exactly, so no existing caller's
results change.

Fusion weights are **hand-set defaults** (`bm25_stem 1.0`, `char_ngram 0.8`,
`lsa 0.6`, RRF `k=60`). They were not tuned. See §7 for why that is stated as a
limitation rather than presented as optimal.

---

## 2. Benchmark

`scripts/make_light_benchmark.py` → `data/synthetic/light_benchmark_v1/`.

| item | value |
|---|---|
| materials / chunks | 168 / 294 (42 paid materials contribute metadata chunks only) |
| topics / concepts | 14 / 42 |
| cases | 104 → 84 relevance, 12 off-topic refusal, 8 constraint |
| split | 73 dev / 31 holdout, assigned by salted hash of `case_id` |

Frozen hashes:

| file | sha256 |
|---|---|
| `catalog.json` | `f7957139a4b0bbcceac931d57b9a9780089a8fb132fbe9ea9925fdda9a941b64` |
| `queries.json` | `72e89bda7b55b102907bb06a2d289acde99d99b95468fcf0fc7ab548ed919a3c` |
| holdout case-id digest | `8c9bacaa754a8dcafbf1dbe77678f53061ce09f86b5cc2138150a6972cf7bb85` |

Grading: the targeted material is 2, other materials of the same topic are 1,
everything else is 0. Every material is graded, so no top-10 key is ever unjudged.

Two query families per concept, both targeting the same material:

* **natural** — the concept's own wording plus a scope phrase
  (`как посчитать юнит-экономику продукта для интернет-магазина`);
* **paraphrase** — a different wording that shares few or no surface forms with the
  indexed text (`как считать экономику клиента и прибыль с клиента для ...`).

The paraphrase family is the morphology stress test. It is **built to be hard for
lexical matching**, so a gain there is expected by construction, not discovered.

---

## 3. Results — development set (73 cases, 59 relevance)

| engine | family | NDCG@10 (95% CI) | Success@5 (95% CI) | Recall@50 | refused | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| tfidf | natural | 0.634 [0.514, 0.743] | 0.840 [0.680, 0.960] | 0.920 | 0.080 | 8.81 | 10.54 |
| tfidf | paraphrase | 0.284 [0.184, 0.393] | 0.441 [0.294, 0.618] | 0.882 | 0.118 | 8.81 | 10.54 |
| bm25 | natural | 0.601 [0.486, 0.706] | 0.840 [0.680, 0.960] | 0.920 | 0.080 | 0.35 | 0.98 |
| bm25 | paraphrase | 0.207 [0.122, 0.294] | 0.353 [0.206, 0.529] | 0.559 | 0.294 | 0.35 | 0.98 |
| bm25_stem | natural | 0.753 [0.692, 0.813] | 1.000 [1.000, 1.000] | 1.000 | 0.000 | 0.86 | 1.55 |
| bm25_stem | paraphrase | 0.379 [0.289, 0.468] | 0.647 [0.471, 0.794] | 0.824 | 0.029 | 0.86 | 1.55 |
| char_ngram | natural | 0.825 [0.784, 0.868] | 1.000 [1.000, 1.000] | 1.000 | 0.000 | 2.69 | 3.64 |
| char_ngram | paraphrase | 0.477 [0.375, 0.571] | 0.647 [0.471, 0.794] | 0.882 | 0.000 | 2.69 | 3.64 |
| lsa | natural | 0.789 [0.731, 0.846] | 1.000 [1.000, 1.000] | 1.000 | 0.000 | 2.70 | 3.48 |
| lsa | paraphrase | 0.459 [0.353, 0.570] | 0.588 [0.441, 0.735] | 0.824 | 0.000 | 2.70 | 3.48 |
| **light_hybrid** | natural | **0.805 [0.763, 0.852]** | **1.000** | 1.000 | 0.000 | 14.94 | 18.69 |
| **light_hybrid** | paraphrase | **0.434 [0.346, 0.522]** | **0.676 [0.529, 0.824]** | 0.912 | 0.029 | 14.94 | 18.69 |

Off-topic refusal rate (dev, 9 cases): `tfidf 1.000`, `bm25 1.000`,
`bm25_stem 1.000`, `lsa 1.000`, **`char_ngram 0.818`**, `light_hybrid 1.000`.

### Paired differences (dev, 59 relevance cases; positive = left is better)

| comparison | NDCG@10 Δ (95% CI) | W/L/T | Success@5 Δ (95% CI) | W/L/T |
|---|---|---|---|---|
| light_hybrid − bm25 | **+0.218 [+0.149, +0.290]** | 39/7/13 | **+0.254 [+0.136, +0.373]** | 16/1/42 |
| light_hybrid − tfidf | **+0.159 [+0.087, +0.232]** | 36/10/13 | **+0.203 [+0.085, +0.322]** | 13/1/45 |
| light_hybrid − bm25_stem | +0.054 [+0.020, +0.091] | 25/9/25 | +0.017 [−0.034, +0.068] | 2/1/56 |
| light_hybrid − char_ngram | **−0.033 [−0.073, +0.003]** | 15/24/20 | +0.017 [−0.034, +0.068] | 2/1/56 |
| light_hybrid − lsa | −0.008 [−0.047, +0.026] | 21/18/20 | +0.051 [+0.000, +0.119] | 3/0/56 |
| bm25_stem − bm25 | +0.164 [+0.107, +0.221] | 33/4/22 | +0.237 [+0.136, +0.356] | 14/0/45 |

---

## 4. Results — frozen holdout (31 cases, 25 relevance)

Reported once, after the configuration was fixed. No parameter was changed after
this table was produced.

| engine | family | NDCG@10 (95% CI) | Success@5 (95% CI) | Recall@50 | refused | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| tfidf | natural | 0.721 [0.587, 0.831] | 0.941 [0.824, 1.000] | 0.941 | 0.059 | 8.19 | 9.36 |
| tfidf | paraphrase | 0.274 [0.097, 0.507] | 0.375 [0.125, 0.750] | 1.000 | 0.000 | 8.19 | 9.36 |
| bm25 | natural | 0.626 [0.507, 0.727] | 0.941 [0.824, 1.000] | 0.941 | 0.059 | 0.39 | 0.83 |
| bm25 | paraphrase | 0.174 [0.031, 0.358] | 0.375 [0.125, 0.750] | 0.875 | 0.000 | 0.39 | 0.83 |
| bm25_stem | natural | 0.793 [0.725, 0.862] | 1.000 [1.000, 1.000] | 1.000 | 0.000 | 0.91 | 1.55 |
| bm25_stem | paraphrase | 0.417 [0.180, 0.631] | 0.625 [0.250, 0.875] | 0.875 | 0.000 | 0.91 | 1.55 |
| char_ngram | natural | 0.866 [0.814, 0.918] | 1.000 [1.000, 1.000] | 1.000 | 0.000 | 2.72 | 3.51 |
| char_ngram | paraphrase | 0.344 [0.162, 0.523] | 0.625 [0.250, 0.875] | 0.750 | 0.000 | 2.72 | 3.51 |
| lsa | natural | 0.807 [0.752, 0.866] | 1.000 [1.000, 1.000] | 1.000 | 0.000 | 2.63 | 4.80 |
| lsa | paraphrase | 0.488 [0.204, 0.762] | 0.625 [0.250, 0.875] | 0.875 | 0.000 | 2.63 | 4.80 |
| **light_hybrid** | natural | **0.824 [0.760, 0.891]** | **1.000** | 1.000 | 0.000 | 12.13 | 17.03 |
| **light_hybrid** | paraphrase | **0.418 [0.173, 0.613]** | **0.625 [0.250, 0.875]** | 0.875 | 0.000 | 12.13 | 17.03 |

Off-topic refusal rate (holdout, 3 cases — n is too small to interpret): 1.000 for
every engine including `char_ngram`.

### Paired differences (holdout, 25 relevance cases)

| comparison | NDCG@10 Δ (95% CI) | W/L/T | Success@5 Δ (95% CI) | W/L/T |
|---|---|---|---|---|
| light_hybrid − bm25 | **+0.213 [+0.127, +0.309]** | 17/1/7 | +0.120 [+0.000, +0.240] | 3/0/22 |
| light_hybrid − tfidf | **+0.116 [+0.012, +0.227]** | 12/8/5 | +0.120 [+0.000, +0.240] | 3/0/22 |
| light_hybrid − bm25_stem | +0.021 [−0.001, +0.044] | 9/3/13 | 0.000 | 0/0/25 |
| light_hybrid − char_ngram | −0.005 [−0.056, +0.056] | 5/9/11 | 0.000 | 0/0/25 |
| light_hybrid − lsa | −0.011 [−0.061, +0.036] | 8/7/10 | 0.000 | 0/0/25 |
| bm25_stem − bm25 | +0.191 [+0.099, +0.291] | 12/1/12 | +0.120 [+0.000, +0.240] | 3/0/22 |

The holdout reproduces the dev ordering. The gains over TF-IDF and lexical BM25 are
the same size on both splits, which is the only reason to trust them at all given
31 holdout cases.

---

## 5. Constraint cases

8 cases (3 dev / 5 holdout) where the natural answer is excluded by
`budget_preference=free_only`, `formats`, or `available_time_minutes`.

| check | result |
|---|---|
| constraint violations across all engines, dev + holdout | **0** |
| cases returning at least one result | 8 / 8 for every engine |

The eligibility filters are inherited unchanged from `prepare_corpus` /
`eligible_for_context`, so this is a regression check on that inheritance, not a
new feature.

---

## 6. Acceptance criteria — status

| criterion | status |
|---|---|
| four word-form cases retrieve the same material | **met** — `test_word_forms_retrieve_the_same_material` (top-3) and `test_stemmed_channel_order_is_form_invariant` (exact ordering on the stemmed channel) |
| test06-style paraphrase recovered without E5 | **met in structure**: paraphrase NDCG@10 0.284 → 0.434 (dev), 0.274 → 0.418 (holdout). The specific stage-5 podcast cannot be tested without the real catalog |
| lunar-landing / chemical-element queries return a precise no-match | **met** on the 12 synthetic off-topic queries: `no_eligible` + `query_out_of_domain`, empty candidates |
| precise status instead of generic `needs_clarification` | **met** — `no_eligible` with `query_out_of_domain` (zero coverage) or `insufficient_query_coverage` (partial), distinct from `empty_query` |
| not worse than current BM25 on dev | **met**, by a wide margin (§3) |
| refusal rate improves over the incumbent | **not met — and the premise is false here.** TF-IDF and BM25 already refuse 100% of this benchmark's off-topic queries. What the guard actually prevents is the regression that the naked char-ngram channel shows (0.818 dev). |
| warm p95 latency under ~100 ms on CPU | **met at this scale**: 18.69 ms p95 (dev), 17.03 ms (holdout). Scale caveat in §7 |
| E5 and hybrid-with-E5 measured | **not measured** — no weights or vectors in this repository |

---

## 7. Latency, and why it does not generalise yet

Measured warm (one untimed pass first), per query, `k=50`, on 168 materials /
294 chunks:

| engine | p50 ms | p95 ms |
|---|---|---|
| bm25 | 0.35 | 0.98 |
| bm25_stem | 0.86 | 1.55 |
| char_ngram | 2.69 | 3.64 |
| lsa | 2.70 | 3.48 |
| tfidf (production) | 8.81 | 10.54 |
| light_hybrid | 14.94 | 18.69 |

The hybrid costs roughly 3–4× the sum of its parts because it queries all three
channels, fuses, then re-analyses the evidence chunk of every candidate for the
synonym boost and the reason text.

**The catalog here is 8.6× smaller than production** (168 vs ≈1,444 materials,
294 vs ≈9,965 chunks). Latency is dominated by per-query work (three channel
lookups + fusion), but the LSA projection and the evidence analysis scale with
catalog size. The `<100 ms` target is therefore **plausible but unverified at
production scale**. Do not quote "18 ms" as a production figure.

Also: the index is refit deterministically on load rather than deserialised
(`light_index.py`), which is a *startup* cost of seconds, not a query cost. That
trade was made to keep the artifact auditable and pickle-free.

---

## 8. What this evaluation does not measure

1. **Real relevance.** Labels are construction-derived. The benchmark rewards
   finding the material that generated the query. It cannot tell you whether a
   real entrepreneur would find the answer useful.
2. **Production scale.** See §7.
3. **E5 value.** Unmeasured. No weights, no vectors.
4. **The production failure mode from `docs/quality_stage56.md`.** The claim was
   that TF-IDF returns 16 business materials for a lunar-landing query. With the
   current coverage guard, TF-IDF refuses all 12 of this benchmark's off-topic
   queries. Either the production failure predates the guard, or it involved a
   query with partial vocabulary overlap. **This benchmark cannot reproduce it**, so
   the claim "the light path fixes the lunar-landing query" is only demonstrated
   for the zero-overlap case, in a unit test.
5. **Typos.** Not in v1. The char n-gram channel should help; that is an
   expectation, not a measurement.
6. **History/personalisation.** All cases are single-query with no profile.
7. **Two-annotator agreement.** No human judgments exist to compare.
8. **Weight quality.** The fusion weights are hand-set. A dev-only sweep might
   close the 0.033 NDCG gap to `char_ngram`, but 59 dev cases are few enough that
   such a sweep would likely fit noise. Left as future work with that caveat.

---

## 9. Failure analysis (dev, observed)

**Paraphrases with no shared vocabulary fail for every lexical engine.** Examples
where `light_hybrid` returns the wrong top-1:

| query | target | what came back |
|---|---|---|
| `где искать клиентов для бизнеса` | Каналы привлечения | Кредит для бизнеса, Масштабирование бизнеса |
| `что говорить клиенту по телефону` | Скрипты звонков | Удержание покупателей, Клиентский сервис |
| `как работать по усн` | Упрощённая система | НДС |
| `как убрать ручную работу из процессов` | Автоматизация рутины | Работа с жалобами |

These need semantics. Stemming, char n-grams and a 120-component LSA over 168
documents are not enough, and it would be dishonest to present the +0.15 NDCG as
solving them.

**One false refusal from the coverage guard.** `как улучшить оценки магазина`
returns `no_eligible` with `insufficient_query_coverage`: `магазин` is indexed only
inside the hyphenated token `интернет-магазине`, so the guard sees 0 of 3 terms
covered. 1 of 34 dev paraphrase cases (2.9%). This is a real precision/recall
trade-off in the guard, and it is the mechanism's main visible cost.

**The naked char n-gram channel matches off-topic queries.** `почему болит голова
утром` returns a "Карточка товара" material; `как выучить китайский язык` returns a
"Клиентский сервис" material. The fusion-level guard suppresses these, which is the
concrete reason the hybrid exists rather than shipping `char_ngram` alone.

---

## 10. Reproduction

```powershell
# from the repository root
$env:PYTHONUTF8=1

# 1. build (or verify) the benchmark — idempotent, refuses to overwrite without --force
python scripts/make_light_benchmark.py

# 2. run all six engines, dev and holdout, write raw results
python scripts/evaluate_light_retrieval.py `
    --json data/synthetic/light_benchmark_v1/results_light_v1.json

# 3. behavioural tests for the light path
python -m pytest backend/tests/test_light_retrieval.py -q

# 4. full suite
python -m pytest backend/tests -q
```

Raw per-case numbers, CIs and paired deltas:
`data/synthetic/light_benchmark_v1/results_light_v1.json`.
