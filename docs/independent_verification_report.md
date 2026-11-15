# Independent verification report — `light-hybrid-search-v2`

**Question:** under the project constraints (no LLM calls, no transformer weights in the
default path, CPU only, light dependencies), is `light-hybrid-search-v2` the best
retrieval configuration, and is it better than `light-hybrid-search-v1` on paraphrased
queries?

**Answer:** **No, not as "best".** v2 is reliably better than v1 on dev, but the
holdout paraphrase gain is **not** significant once the paired test is restricted to the
8 holdout paraphrase cases (`+0.045 [−0.007, +0.106]`). v2 and `char_ngram` are a
statistical tie on the metric the claim rests on, and `char_ngram` is ~4.7× faster.
v2 remains defensible as the *safest* default (better Success@5, 12/12 OOD refusal),
not as the best-NGCG default.

This report was produced by an independent verifier, not by the author of v2. The
protocol is `docs/independent_verification_brief.md`. Everything below is measured on
this machine unless explicitly marked **documented only**.

| check | result |
|---|---|
| frozen hashes match `manifest.json` | **PASS** |
| benchmark reproduction (all 7 engines) | **PASS** (NDCG/Success/Recall match; ms differ) |
| test suite | **PASS** — `275 passed, 47 skipped` |
| C4 invariants (dups, caps, filters, determinism, paid rows) | **PASS** — all zero |
| C5 OOD guard (v2) | **PASS** — 12/12 refused, 1/84 false refusals |
| sub-claim 1, dev paraphrase | **PASS** — `+0.044 [+0.020, +0.069]` |
| sub-claim 1, holdout paraphrase (decision rule) | **FAIL** — `+0.045 [−0.007, +0.106]` |
| sub-claim 1, holdout pooled relevance (diagnostic) | PASS — `+0.028 [+0.009, +0.050]` |
| no natural regression | **PASS** — dev `+0.013`, holdout `+0.020` |
| sub-claim 2, "best defensible" | **FAIL** — tie with `char_ngram` |
| **VERDICT** | **`tie-with-char_ngram`, not best** |

Environment: Windows 11, Python 3.12.10, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1,
pandas 3.0.6, CPU only. Branch `lead`, head `9dd1a77` (the brief expected `4cb1d6a`;
`9dd1a77` only adds the verification brief, so the benchmark and code are identical).
GitHub: `https://github.com/alihosseinabadi/alfa_bank/tree/lead`.

---

## 1. What was verified, and how

The brief defines two sub-claims:

1. v2 > v1 on paraphrase NDCG@10, reproducibly on dev **and** frozen holdout.
2. v2 is the best defensible choice against `char_ngram`, `lsa`, `bm25_stem`, `tfidf`.

The rule for sub-claim 1 is explicit: *"the holdout paraphrase Δ is positive and its
paired 95% CI excludes 0"*. The rule for sub-claim 2 requires v2 to beat `char_ngram`
on holdout with a CI excluding 0, **or** the report to say plainly that they tie.

All exploration was on **dev only**. The holdout was read once for the final candidate
(`semantic_only`, frozen before the read) and was then re-scored deterministically for
the v2/v1 and v2/char family-restricted CIs reported here. No configuration was changed
after any holdout number was seen. The re-scoring is analysis of already-produced
rankings, not a second model-selection read.

Paired bootstrap: 2,000 rounds, seed 7, same query set on both sides, implemented in
`scripts/evaluate_light_retrieval.py::bootstrap_ci`. "Tie" means the 95% CI includes
zero. About **40 distinct paired comparisons** are reported: 20 family-level (five
engine pairs × natural/paraphrase × dev/holdout), 8 pooled, 4 top-1, 1 component-count,
and 7 on the new query set. With that many comparisons, isolated "significant" results
at p≈0.05 should be read cautiously; the main conclusions rest on replication across dev
and holdout, not on one CI.

---

## 2. Frozen artifacts and reproduction

### 2.1 Hashes (must pass before any number is trusted)

```powershell
$env:PYTHONUTF8=1
python -c "import hashlib,json;from pathlib import Path;b=Path('data/synthetic/light_benchmark_v1');m=json.loads((b/'manifest.json').read_text(encoding='utf-8'));[print('sha',n,hashlib.sha256((b/n).read_bytes()).hexdigest()==m['files'][n],hashlib.sha256((b/n).read_bytes()).hexdigest()) for n in ('catalog.json','queries.json')];q=json.loads((b/'queries.json').read_text(encoding='utf-8'));ids=sorted(c['case_id'] for c in q['cases'] if c['split']=='holdout');d=hashlib.sha256('\n'.join(ids).encode()).hexdigest();print('holdout digest match',d==m['holdout_hash'],d);print('cases',len(q['cases']),'holdout',len(ids))"
```

Output:

```
sha catalog.json True f7957139a4b0bbcceac931d57b9a9780089a8fb132fbe9ea9925fdda9a941b64
sha queries.json True 72e89bda7b55b102907bb06a2d289acde99d99b95468fcf0fc7ab548ed919a3c
holdout digest match True 8c9bacaa754a8dcafbf1dbe77678f53061ce09f86b5cc2138150a6972cf7bb85
cases 104 holdout 31
```

All three match the brief. Shape is 104 cases (73 dev / 31 holdout, 59 dev and 25
holdout relevance cases).

I did **not** run `scripts/make_light_benchmark.py`; the hashes already match the
manifest and running the generator writes into the frozen directory. This is a
deliberate deviation from the "five commands", and it is why the hash check is reported
first.

### 2.2 Test suite

```powershell
$env:PYTHONUTF8=1; python -m pytest backend/tests -q
```

```
275 passed, 47 skipped, 231 warnings in 41.23s
```

Matches the brief. 46 skips need `ALFA_EVENTS_TEST_DATABASE_URL`; 1 needs a missing
optional artifact. Without `PYTHONUTF8=1` the suite produces ~78 cp1252 decode errors;
those are environmental and were not counted as failures.

### 2.3 Benchmark reproduction

```powershell
$env:PYTHONUTF8=1; python scripts/evaluate_light_retrieval.py `
  --json "$env:TEMP\opencode\verify\results_repro.json"
```

Reproduced dev and holdout tables for all seven engines. NDCG@10, Success@5 and
Recall@50 match the committed numbers to rounding. Latency does **not** match the doc:

| run | v2 dev p50 / p95 | v2 holdout p50 / p95 |
|---|---|---|
| `docs/semantic_search_v2.md` | 15.55 / 18.96 ms | 8.12 / 12.76 ms |
| this machine, one pass | 8.65 / 11.16 ms | 8.24 / 11.06 ms |
| this machine, 5 warm passes, median of p50s | 8.99 ms | — |

The dev difference is ~1.8×; the holdout difference is small. This confirms H5
(latency is machine/load-specific) and means the absolute ms should not be quoted as a
property of the algorithm. Warm p50 order is stable: `char_ngram` 1.93 < `tfidf` 5.13 <
`semantic_only` 8.51 < v1 8.69 < v2 8.99 ms.

---

## 3. Reproduced engine table (dev, 59 relevance cases)

| engine | natural NDCG@10 | paraphrase NDCG@10 | paraphrase Success@5 | paraphrase Recall@50 | false refusals |
|---|---|---|---|---|---|
| tfidf | 0.634 | 0.284 | 0.441 | 0.882 | 7/84 |
| bm25 | 0.601 | 0.207 | 0.353 | 0.559 | 13/84 |
| bm25_stem | 0.753 | 0.379 | 0.647 | 0.824 | 1/84 |
| char_ngram | **0.825** | 0.477 | 0.647 | 0.882 | 0/84 |
| lsa | 0.789 | 0.459 | 0.588 | 0.824 | 0/84 |
| light_hybrid (v1) | 0.805 | 0.434 | 0.676 | 0.912 | 1/84 |
| **light_hybrid_v2** | 0.818 | **0.478** | **0.735** | **0.912** | 1/84 |

The v2 doc's table is accurate. v2's real advantages are Success@5 (+0.088 over
`char_ngram`) and recall (0.912), not NDCG@10, where it is inside noise of `char_ngram`.

Holdout (25 relevance cases) reproduces as well: v2 natural 0.844, paraphrase 0.463;
`char_ngram` natural **0.866**, paraphrase 0.344; `lsa` paraphrase 0.488. No single
engine wins both families — but `char_ngram` wins the natural half and is 1.000 top-1
there, while v2's paraphrase advantage over it is not significant (`+0.119 [−0.012,
+0.274]`, n=8).

---

## 4. Decision-rule accounting

### Sub-claim 1 — v2 > v1 on paraphrase

| split | v1 | v2 | paired Δ (paraphrase only) | W/L/T |
|---|---|---|---|---|
| dev (34) | 0.434 | 0.478 | **+0.044 [+0.020, +0.069]** | 18/4/12 |
| holdout (8) | 0.418 | 0.463 | +0.045 [−0.007, +0.106] | 4/2/2 |

**Dev passes; holdout fails the stated rule.** The direction and size are consistent
(+0.044 vs +0.045), so this is a power problem (n=8), not evidence that the effect is
absent. But the brief's rule is explicit about the CI, and the CI includes zero.

The number quoted in the brief and in `docs/semantic_search_v2.md` — holdout
`+0.028 [+0.009, +0.050]` — is the pooled **all-relevance** delta (17 natural + 8
paraphrase), not the paraphrase delta. Pooling is how it clears zero: v2 also improves
natural by `+0.020 [+0.006, +0.036]`. See §6.1.

### Sub-claim 2 — best defensible

| comparison | dev | holdout |
|---|---|---|
| v2 − `char_ngram`, pooled | −0.002 [−0.039, +0.032] | +0.023 [−0.035, +0.092] |
| v2 − `char_ngram`, paraphrase | +0.001 [−0.055, +0.057] | +0.119 [−0.012, +0.274] |
| v2 − `char_ngram`, natural | −0.007 [−0.041, +0.025] | −0.022 [−0.078, +0.020] |
| v2 − `lsa`, paraphrase | +0.019 [−0.053, +0.082] | −0.025 [−0.104, +0.055] |
| v2 − `bm25_stem`, pooled | +0.085 [+0.048, +0.125] | — |
| v2 − `tfidf`, pooled | +0.190 [+0.121, +0.261] | +0.144 [+0.041, +0.257] |

Every v2 − `char_ngram` and v2 − `lsa` CI includes zero on both splits. `char_ngram`
also wins the natural half of the holdout and is 4.7× faster. The rule therefore
resolves to **tie-with-char_ngram**, not "best".

### Other rule conditions

- **Natural regression:** dev `+0.013 [−0.011, +0.036]`, holdout `+0.020 [+0.006,
  +0.036]` — no fall, rule passes. Per-case, two natural queries lose NDCG
  (`−0.147`, `−0.138`), but the mean condition in the brief is met.
- **Constraints:** 0 violations across all 104 cases for every engine. The 3 dev and
  5 holdout constraint cases are answered with eligible materials.
- **Refusal:** v2 refuses 12/12 OOD; false-refusal rate 1/84 = 1.2%. Rule passes. The
  known false refusal persists: `как улучшить оценки магазина для онлайн-школы` returns
  nothing (`top1=None`).
- **C4 invariants:** duplicates 0, candidates over the cap 0, filter violations 0,
  nondeterministic results 0, paid/protected rows in the fitted index 0 — all engines,
  all 104 cases.
- **C5 OOD guard:** tfidf 12/12, bm25 12/12, bm25_stem 12/12, `char_ngram` **10/12**,
  lsa 12/12, v1 12/12, v2 12/12. `char_ngram` accepts 2 of 12 off-topic queries; any
  proposal to make it the default needs a separate BM25-based guard.

---

## 5. Falsification experiments

### H1 — `char_ngram` alone is as good and much faster → **confirmed on quality**

Dev paraphrase 0.477 vs 0.478; natural 0.825 vs 0.818; all CIs include zero. It is
1.93 ms vs 8.99 ms warm p50 (4.7×). What v2 buys for that cost: paraphrase Success@5
0.735 vs 0.647, recall 0.912 vs 0.882, and a 12/12 OOD guard vs 10/12. So the fused
path is justified by **safety and head-coverage**, not NDCG. The docs should say that.

### H2 — a different component count beats 40 → **confirmed on NDCG, already disclosed**

Dev paraphrase with the shipped weights: 10 → 0.462, **20 → 0.512**, 30 → 0.496,
**40 → 0.478**, 50 → 0.481, 60 → 0.481, 80 → 0.477, 120 → 0.474. Paired 20 − 40 =
`+0.034 [+0.013, +0.058]`, W/L/T 17/3/14. But 20 components has top-1 0.294 vs 0.412
for 40. `docs/semantic_search_v2.md` §2 already lists 20 components at 0.488 with worse
top-1 and explicitly rejects lower counts for "flattening the head"; that is an honest
and correct trade-off, not a contradiction. The v2 doc's narrower plateau claim
(±0.2 semantic weight, synonym weight 0.3–0.5 → ≤0.005) reproduces almost exactly:
semantic weight 0.8/1.0/1.2 gives 0.4719/0.4781/0.4813; synonym weight
0.3/0.4/0.5 gives 0.4721/0.4744/0.4781 (max move 0.006, marginally above the stated
0.005). However, synonym weight **0.6–0.75** gives 0.4926–0.4951 and top-1 0.678 (vs
0.661 at 0.5), i.e. +0.015 paraphrase at no top-1 cost. That is a dev-only lead and was
**not** promoted, because the holdout had already been read.

### H3 — the semantic channel adds nothing over v1 → **rejected**

Dev paraphrase v2 − v1 = `+0.044 [+0.020, +0.069]`. Ablations (dev paraphrase):
`v2_nosem` 0.447, `v2_no_syn` 0.465, `v2_equal` 0.478, v2 0.478. Most of the gain is
the material-level LSA; the synonym dictionary adds ~0.013. Removing the semantic
channel entirely loses ~0.031.

### H4 — the gain is one outlier → **rejected**

29/7/23 in the original table; dropping the three largest v2−v1 gains moves the dev
mean from +0.031 to **+0.0204**, still positive. The gain is spread over the
distribution, though small.

### H5 — latency is machine-specific → **confirmed**

Doc 15.55 ms vs this machine 8.65 ms on the same dev cases; warm 5-pass median 8.99 ms.
Do not quote a single absolute latency number.

### H6 — post-holdout dictionary tuning → **no evidence found**

`data/synonyms_ru.json` was added in `de97666`, before the benchmark (`2b6d6b5`) and
never modified afterwards (`git log --all -- data/synonyms_ru.json` returns one commit).
The v2 change `02ecb80` did not touch the dictionary. This does not prove intent, but
there is no commit-level evidence of leakage. The dictionary note says it was seeded from
catalog topics/tags, which is expected.

### H7 — the benchmark's paraphrases are lexically easy → **confirmed as a validity limit**

Stem overlap between query and top target: natural mean 0.731, paraphrase mean 0.476;
**no dev case is below 0.2**. Correlation between overlap and v2−v1 gain is −0.176.
Buckets: 0.2–0.4 (n=6) +0.009; 0.4+ (n=53) +0.034. So the measured "semantic" gain
happens on paraphrases that still share roughly half their stems with the target. It is
not evidence of zero-overlap semantic matching.

### H8 — new, independently written queries → **does not favor v2**

24 relevance queries (8 paraphrase, 5 typo, 5 slang, 3 short, 3 long), written before
inspecting engine output, plus 8 OOD queries; single annotator. Grades follow the
benchmark construction (target=2, same-topic=1, else 0).

| engine | paraphrase (8) | typo (5) | slang (5) | short (3) | long (3) | all (24) |
|---|---|---|---|---|---|---|
| tfidf | 0.061 | 0.139 | 0.241 | 0.897 | 0.261 | 0.244 |
| bm25_stem | 0.041 | 0.418 | 0.244 | 0.898 | 0.230 | 0.292 |
| char_ngram | 0.041 | 0.774 | 0.285 | 0.937 | 0.563 | 0.422 |
| **lsa** | **0.270** | 0.730 | **0.598** | 0.911 | 0.533 | **0.547** |
| v1 | 0.204 | 0.592 | 0.583 | 0.945 | 0.583 | 0.504 |
| v2 | 0.157 | 0.617 | 0.543 | **0.985** | 0.570 | 0.488 |
| semantic_only | 0.149 | 0.641 | 0.533 | 0.845 | 0.529 | 0.466 |

All pairwise CIs include zero at n=24. v2 is not the best engine here (lsa is
numerically ahead), and the paraphrase subset collapses from 0.478 on the benchmark to
0.157 on these harder paraphrases. OOD: every engine refuses 8/8 except `char_ngram`
(6/8, accepting "подготовиться к марафону" and "настроить принтер"). Caveats: one
annotator, no inter-annotator agreement, and the labels use the same construction rule as
the benchmark.

### H9 — the result depends on catalog size → **confirmed as fragility**

50% catalog subsample (seed 7, 26 dev cases with a surviving positive): `char_ngram`
0.664 natural / 0.477 paraphrase; v2 0.650 / 0.471; v1 0.660 / 0.455; lsa 0.626 / 0.431.
v2's advantage disappears. With 168 materials the benchmark is already small; this is a
warning about scaling, not a production estimate.

### H10 — worst dev queries → **failure modes are real**

v2 returns NDCG 0 on several paraphrases, including `как продавать товар клиенту для
оптовой компании` (top-1 is a marketplace card, not the sales script), `что говорить
клиенту по телефону…`, and the false refusal above. On
`как считать экономику клиента и прибыль с клиента…` `char_ngram` scores 0.720 while
v2 scores 0.280. These are the cases a user would notice; aggregate NDCG hides them.

### Candidate found during verification — `semantic_only`

Frozen as `LightRetrievalPolicyV2(channel_weights={"bm25_stem": 0, "char_ngram": 0,
"semantic": 1})`, all other parameters at shipped defaults.

| split / family | v2 | semantic_only | paired Δ | W/L/T |
|---|---|---|---|---|
| dev paraphrase | 0.478 | **0.569** | **+0.091 [+0.035, +0.152]** | 21/8/5 |
| dev natural | 0.818 | **0.863** | +0.045 [+0.006, +0.086] | 11/6/8 |
| holdout paraphrase | 0.463 | 0.503 | +0.039 [−0.037, +0.116] | 5/2/1 |
| holdout natural | 0.844 | 0.879 | +0.035 [−0.019, +0.099] | 8/6/3 |

It looks better on dev, but: holdout does not confirm it; natural **top-1 falls from
1.000 to 0.920 dev and 0.824 holdout** (holdout Δ `−0.176 [−0.353, 0.000]`); and on the
24 new queries it scores 0.466 vs v2 0.488 (`−0.022 [−0.050, +0.008]`). It is a
legitimate idea for a follow-up, not a replacement.

---

## 6. Contradictions with `docs/semantic_search_v2.md`

### 6.1 The holdout significance is pooled, not paraphrase-specific (substantive)

The doc shows family means, then a "paired differences" table, then writes (line 126):
*"The dev gain reproduced on the holdout at almost the same size, with the paired CI
excluding zero."* In context this reads as the paraphrase gain. Restricting the pairing
to the 8 holdout paraphrase cases gives `+0.045 [−0.007, +0.106]` — **including zero**.
The `+0.028 [+0.009, +0.050]` figure is the pooled 25-case relevance delta; it is
significant mainly because v2 also improves the 17 natural cases. Same pattern on dev:
pooled +0.031 vs paraphrase-only +0.044. The fix is one sentence: label the delta rows
"all relevance cases" and report the paraphrase-only CI separately.

### 6.2 "Best" is stated more strongly in the brief than in the doc

The doc itself rates v2 4/10 and says `char_ngram` ties on dev. The brief's sub-claim 2
is "not claimed as proven". This report confirms the doc's caution; the contradiction is
with the framing "best retrieval configuration" in the task statement, not with the
doc's own caveats.

### 6.3 Latency numbers are not portable

15.55 ms dev in the doc vs 8.65 ms here; holdout 8.12 vs 8.24. The doc's ms are one
machine, one load. It already says so in the brief §6 H5, but the tables do not carry a
warning.

### 6.4 Minor: plateau tolerance

Stated "≤0.005"; measured max move 0.006 within the stated ranges. Not worth changing,
but the number is slightly optimistic. More relevant: synonym weight 0.6–0.75 is
+0.015 dev paraphrase at no top-1 cost, so "chosen" is a defensible-but-not-optimal
point even inside the explored family.

No contradiction found on: component count choice (20 comps is higher NDCG but lower
top-1, and the doc says so), hash/benchmark construction, C4 invariants, OOD refusal, or
the v1→v2 direction.

---

## 7. What could not be verified

1. **E5.** No weights, vectors, `*.npy`, `*.npz`, `*.safetensors`, `*.bin` or `*.onnx`
   anywhere in the checkout. E5 and any transformer-based comparison are **unmeasured**,
   not "worse".
2. **Real catalog / stage 5–6 private evaluation.** `data/processed/catalog`,
   `data/raw`, `data/interim`, `reports` and `artifacts` are absent, so
   `scripts/build_light_index.py` cannot run and the 1,444-material / 9,965-chunk
   collection in `docs/quality_stage56.md` cannot be reproduced. The benchmark's 168
   materials are the only measurable corpus.
3. **DB-backed tests.** 46 of 47 skips need `ALFA_EVENTS_TEST_DATABASE_URL`; no
   database was available.
4. **Inter-annotator agreement.** H8 has one annotator (the verifier); no second
   labelling, so no κ.
5. **Production latency.** 168 materials, one CPU, one machine; not a production
   estimate.
6. **Intent of the authors.** H6 checks commits, not people. No leakage evidence was
   found, but absence of evidence is not proof.

---

## 8. Recommended action

1. **Do not merge the claim "v2 is the best".** Merge the narrower, true statement:
   *v2 beats v1 on dev and on pooled holdout relevance; its paraphrase-only holdout gain
   is positive but not significant at n=8; it ties `char_ngram` on NDCG and wins on
   Success@5, recall and OOD safety.*
2. **Correct §4/§5 of `docs/semantic_search_v2.md`:** label the paired-delta rows as
   pooled relevance and add the paraphrase-only holdout CI
   `+0.045 [−0.007, +0.106]`. This is a documentation fix, not a re-run.
3. **Choose the default on operational grounds, explicitly.** If OOD refusal and
   top-5 coverage matter more than 4.7× latency, keep v2 and say so. If latency and
   simplicity dominate, `char_ngram` plus a BM25-based OOD guard is the cheaper
   candidate — but it must be measured with the guard attached.
4. **Run one clean external evaluation before any further tuning:** a new query set
   with genuinely lexical-disjoint paraphrases, two annotators, and the production
   catalog. H8 shows the benchmark's paraphrase difficulty is not representative
   (0.478 → 0.157 for v2).
5. **If v2 is kept, consider synonym weight 0.6** (dev +0.015 paraphrase, same top-1),
   but validate on a *new* holdout. Do not re-use this one; it has been read.
6. **Keep the `semantic_only` idea on the backlog.** It has the strongest dev signal
   (+0.091 paraphrase) but loses natural top-1 and does not generalize to the 24 new
   queries.

---

## 9. Reproduction manifest

All commands were run from the repo root with `$env:PYTHONUTF8=1`.

| what | command |
|---|---|
| hashes | the inline Python hash check in §2.1 |
| tests | `python -m pytest backend/tests -q` |
| full benchmark | `python scripts/evaluate_light_retrieval.py --json <out>.json` |
| engine/family metrics | `build_engines` + `context_for_case` + `judged_metrics` from `scripts/evaluate_light_retrieval.py` |
| paired CIs | `bootstrap_ci(deltas)`, 2,000 rounds, seed 7 |
| ablations / sweeps | `LightHybridRetrieverV2(LightRetrievalPolicyV2(...)).fit(materials, chunks)` |
| candidate | `LightRetrievalPolicyV2(channel_weights={"bm25_stem":0.0,"char_ngram":0.0,"semantic":1.0})` |

The verification scripts used for the additional experiments live outside the repo at
`%TEMP%\opencode\verify\` (`verify_core.py`, `verify_candidate.py`, `verify_overlap.py`,
`verify_new_queries.py`). They are deliberately not committed: they are throwaway
harnesses around the committed evaluator, and the report records every configuration and
number needed to re-derive the results. The evaluator, benchmark and code are unchanged.

**Scope of the verdict:** these results apply to the 168-material synthetic benchmark
and the 24 new single-annotator queries. They do not establish production relevance, and
they do not measure E5. Within that scope: v2 is better than v1, is not better than
`char_ngram` on NDCG, and is not the best setup under the brief's decision rule.
