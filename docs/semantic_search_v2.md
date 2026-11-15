# Semantic search v2 — material-level LSA, measured

Date: 2026-11-15. Branch `ml-boost`. New version: `light-hybrid-search-v2`.
`light-hybrid-search-v1`, its policy and its numbers are untouched and stay
selectable.

Scope of the question this document answers: *how far can "semantic" retrieval go
with TF-IDF, SVD, stemming and a curated synonym dictionary only?* No embeddings, no
transformer, no GPU, no training data. The answer is a real but bounded gain, and the
bound is stated in §7.

---

## 1. What changed

| item | v1 | v2 |
|---|---|---|
| semantic channel | LSA over **chunks**, 120 components | LSA over **materials** (all public chunks aggregated), 40 components |
| query vector | `TfidfVectorizer.transform`, no synonym terms | IDF-weighted term vector + curated synonyms at weight 0.5 |
| channels fused | `bm25_stem 1.0`, `char_ngram 0.8`, `lsa 0.6` | `bm25_stem 1.0`, `char_ngram 0.8`, `semantic 1.0` |
| code | `lsa_retriever.py` | `semantic_retriever.py` + `LightHybridRetrieverV2` |

Why material-level: relevance is judged per material, and with 294 chunks a
120-component projection is close to full rank, so v1's LSA barely compresses
anything. 168 material documents with 40 components actually summarise the
catalogue. Why IDF-weighted queries: without it the query vector lives on a
different scale from the documents, and the projection is dominated by long tokens.

The v2 class only overrides construction, channel set, identity payload and the
explanation text. Refusal, eligibility, fusion, synonym post-boost and candidate
shaping are inherited from v1, so the versions cannot drift apart silently.

---

## 2. Dev-only exploration (what was tried, honestly)

All of this ran on the 73 dev cases; the holdout was not read until the
configuration was frozen. Roughly **30 configurations** were evaluated across these
families. That is a lot for 59 relevance cases, and it is the main caveat on the
dev numbers.

| family | dev paraphrase NDCG@10 | dev paraphrase top-1 | verdict |
|---|---|---|---|
| v1 baseline | 0.434 | 0.294 | — |
| material LSA, 120 comps | 0.441 | 0.294 | v1's rank problem persists |
| material LSA, 60 comps | 0.443 | 0.265 | no gain |
| **material LSA, 40 comps** | **0.468** | **0.412** | best single semantic channel |
| material LSA, 20 comps | 0.488 | 0.294 | higher NDCG, worse top-1 |
| corpus-derived thesaurus, 1–3 neighbours | 0.438–0.469 | 0.265–0.324 | no better than curated synonyms |
| synonym-expanded stemmed cosine, w=0.5 | 0.484 | 0.324 | strong standalone, weak in fusion |
| RRF of v1 channels + semantic channel | 0.430–0.443 | 0.294–0.353 | dilution; not enough |
| rerank fused top-20 by semantic similarity | 0.433–0.462 | 0.294–0.353 | costs 0.01–0.02 natural for +0.02 paraphrase |
| **v2: LSA(40) + IDF-weighted synonym query, weights 1.0/0.8/1.0** | **0.478** | **0.412** | chosen |

Chosen because it is the only variant that improved paraphrase **without** lowering
natural NDCG, and because it sits on a plateau: changing the semantic weight by
±0.2 or the synonym weight between 0.3 and 0.5 moves paraphrase by ≤0.005. A sharp
optimum on 59 cases would have been a warning sign, not a result.

Rejected explicitly: the corpus thesaurus (it mostly recovers surface neighbours and
adds noise), two-stage reranking (it trades natural quality for paraphrase), and
lower component counts (they buy NDCG by flattening the head).

---

## 3. Frozen configuration

```
LIGHT_RETRIEVAL_VERSION_V2 = "light-hybrid-search-v2"
channel_weights   = {"bm25_stem": 1.0, "char_ngram": 0.8, "semantic": 1.0}
semantic_components = 40
semantic_synonym_weight = 0.5
semantic_min_similarity = 0.15
rank_constant = 60
```

Benchmark hashes are unchanged (`catalog.json f7957139…`, `queries.json 72e89bda…`,
holdout digest `8c9bacaa…`), so every table below is comparable to
`docs/light_search_evaluation.md`.

---

## 4. Results — dev (73 cases, 59 relevance)

| engine | natural NDCG@10 | paraphrase NDCG@10 | paraphrase Success@5 | p50 / p95 ms |
|---|---|---|---|---|
| tfidf (production) | 0.634 | 0.284 | 0.441 | 8.13 / 10.91 |
| char_ngram | 0.825 | 0.477 | 0.647 | 2.64 / 4.86 |
| lsa (v1 channel) | 0.789 | 0.459 | 0.588 | 2.57 / 4.16 |
| light_hybrid (v1) | 0.805 | 0.434 | 0.676 | 14.72 / 18.42 |
| **light_hybrid_v2** | **0.818** | **0.478** | **0.735** | 15.55 / 18.96 |

Top-1 on paraphrase: **0.294 → 0.412**; target present in top-10: **0.765 → 0.824**.

Paired differences on dev (positive = left is better):

| comparison | NDCG@10 Δ [95% CI] | W/L/T |
|---|---|---|
| v2 − v1 | **+0.031 [+0.014, +0.049]** | 29/7/23 |
| v2 − char_ngram | −0.002 [−0.039, +0.032] | 25/19/15 |
| v2 − tfidf | **+0.190 [+0.121, +0.261]** | 41/9/9 |
| v2 − bm25 | **+0.249 [+0.180, +0.318]** | 46/5/8 |

---

## 5. Results — frozen holdout (31 cases, 25 relevance), read once

| engine | natural NDCG@10 | paraphrase NDCG@10 | paraphrase Success@5 | p50 / p95 ms |
|---|---|---|---|---|
| tfidf (production) | 0.721 | 0.274 | 0.375 | 7.00 / 10.23 |
| char_ngram | 0.866 | 0.344 | 0.625 | 1.58 / 2.28 |
| lsa (v1 channel) | 0.807 | 0.488 | 0.625 | 1.35 / 1.82 |
| light_hybrid (v1) | 0.824 | 0.418 | 0.625 | 7.69 / 11.85 |
| **light_hybrid_v2** | **0.844** | **0.463** | 0.625 | 8.12 / 12.76 |

| comparison | NDCG@10 Δ [95% CI] | W/L/T |
|---|---|---|
| v2 − v1 | **+0.028 [+0.009, +0.050]** | 11/3/11 |
| v2 − char_ngram | +0.023 [−0.035, +0.092] | 9/8/8 |
| v2 − tfidf | **+0.144 [+0.041, +0.257]** | 14/7/4 |
| v2 − bm25 | **+0.241 [+0.152, +0.340]** | 19/1/5 |

Top-1 on paraphrase, holdout: 0.500 for both v1 and v2 (n=8 — one case is 0.125);
target in top-10: 0.625 → 0.750.

The dev gain reproduced on the holdout at almost the same size, with the paired CI
excluding zero. That is the only reason to take +0.03 seriously at n=25. It is a
small effect, and it is not the +0.15 the word "semantic" might suggest.

Constraint cases: 0 violations, 3/3 dev and 5/5 holdout answered. Off-topic
refusal stays 1.000; the single false refusal on
`как улучшить оценки магазина` persists, because the guard is unchanged.

---

## 6. What v2 fixes, and what it still cannot do

Improvements are concentrated in paraphrases that share some vocabulary with the
right material but ranked it below a same-topic neighbour — 29 wins and 7 losses on
dev. Real examples (dev, NDCG@10 change):

| query | target | Δ |
|---|---|---|
| `как считать экономику клиента и прибыль с клиента для интернет-магазина` | Юнит-экономика (ue1) | **+0.280** |
| `как оценить кандидата на встрече для оптовой компании` | Найм (hr2) | **+0.250** |
| `как считать движение денег в компании для интернет-магазина` | Финансы (fn1) | **+0.167** |

The gains are not free. Two **natural** queries got worse, and one of them is the
largest single change in either direction:

| query | target | Δ |
|---|---|---|
| `что можно автоматизировать в рутине для онлайн-школы` | Операции (op2) | **−0.147** |
| `что такое ltv и cac для небольшого кафе` | Юнит-экономика (ue2) | **−0.138** |

That is why natural NDCG rises only 0.805 → 0.818 despite top-1 staying at 1.000: the
semantic channel sometimes promotes a same-topic neighbour above the exact target.
The trade is worth it on this benchmark, but it is a trade, not a free improvement.

Still failing, and unfixable with this toolbox:

| query | target | what comes back |
|---|---|---|
| `где искать клиентов для бизнеса` | Каналы привлечения | Кредит для бизнеса |
| `что говорить клиенту по телефону` | Скрипты звонков | Удержание покупателей |
| `как работать по усн` | Упрощённая система | НДС |
| `как убрать ручную работу из процессов` | Автоматизация рутины | Работа с жалобами |

These need an actual notion of meaning (`привлечение` ≈ `искать клиентов`,
`усн` ≈ `упрощённая система`). A 40-dimensional SVD over 168 documents cannot learn
that from 14 topics, and a hand-written abbreviation list would be fitting the
benchmark, not improving the system.

Latency: the semantic channel adds ~0.8–1.0 ms p50. v2 is **still slower than the
incumbent** (15.6 vs 8.1 ms p50 on dev) and the production-scale caveat is unchanged.

---

## 7. Rating, in the terms the last answer used

**Semantic search: 3/10 → 4/10.** Breakdown of why it is not higher:

| capability | before | now |
|---|---|---|
| finds the right material for a natural query | 0.80 top-1 | **1.00** |
| finds it for a paraphrase (dev) | 0.29 top-1 | **0.41** |
| has it anywhere in the top 10 (dev paraphrase) | 0.77 | **0.82** |
| bridges synonyms | curated list, post-hoc boost only | curated list **inside** the query vector + corpus-level co-occurrence |
| understands meaning without shared words | no | **still no** |

4/10, not 6/10, because 6 of 10 paraphrases still return the wrong material first.
Getting to 6–7 requires embeddings (E5 is wired as optional and remains
**unmeasured** — no weights here) or a much larger corpus for the co-occurrence
signal. Both are outside the constraints of this task, and neither is claimed.

---

## 8. Reproduction

```powershell
# from the repository root
$env:PYTHONUTF8=1

python scripts/evaluate_light_retrieval.py `
    --json data/synthetic/light_benchmark_v1/results_light_v2.json

python -m pytest backend/tests/test_light_retrieval.py backend/tests/test_semantic_retrieval.py -q

# build/verify an index for the new version
python scripts/build_light_index.py --version v2 --catalog-dir data/processed/catalog
```

`data/processed/catalog` is absent in this repository, so the last command could not
be run here; the save/load round-trip is covered by
`test_v2_index_roundtrip` instead.
