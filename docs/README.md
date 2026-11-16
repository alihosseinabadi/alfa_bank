# Documentation

Deep-dive references for the Alfa-Kurs recommendation engine. Start with the root
[README](../README.md) for the project overview, then read these in order.

| File | Answers |
|---|---|
| [system_design.md](system_design.md) | How the whole system works end to end |
| [ml_architecture.md](ml_architecture.md) | Retrieval, bandit, rewards, features |
| [feature_engineering.md](feature_engineering.md) | The context vector contract: layout, encoding, normalization |
| [linucb_explained.md](linucb_explained.md) | The LinUCB math, variable by variable |
| [reward_design.md](reward_design.md) | Reward policy, attribution, duplicate guards |
| [database_design.md](database_design.md) | Canonical impression table, keys, indexes, ERD |
| [api_documentation.md](api_documentation.md) | Every endpoint, request and response |
| [evaluation_methodology.md](evaluation_methodology.md) | Seeds, metrics, fairness and leakage tests |
| [data_provenance.md](data_provenance.md) | What data is real vs synthetic |
| [presentation_guide.md](presentation_guide.md) | Demo script for the judges |

## Reading paths

**Judge / reviewer:** `system_design.md` → `evaluation_methodology.md` → `data_provenance.md` → `presentation_guide.md`

**Engineer joining the build:** root `DEVELOPMENT_GUIDE.md` → `ml_architecture.md`
→ `feature_engineering.md` → `linucb_explained.md` → `database_design.md`
→ `api_documentation.md`

**ML-focused reader:** `feature_engineering.md` → `linucb_explained.md`
→ `reward_design.md` → `evaluation_methodology.md`

## Conventions used in these docs

- `x` is a context vector (one row), `A` is a matrix, `b` is a vector.
- `K` is the number of course categories; `d = 4K + 15`.
- "candidate" = a course returned by retrieval and eligible for ranking.
- "impression" = a row in `recommendation_impressions`, i.e. a course actually shown.
- "slate" = the set of impressions returned together by one recommendations call.
- "reward" = a scalar derived from one interaction event.
- All numeric examples are **simulated**, never production metrics.
