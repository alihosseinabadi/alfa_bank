# Documentation

Deep-dive references for the Alfa-Kurs recommendation engine. Start with the root
[README](../README.md) for the project overview, then read these in order.

| File | Answers |
|---|---|
| [system_design.md](system_design.md) | How the whole system works end to end |
| [ml_architecture.md](ml_architecture.md) | Retrieval, bandit, rewards, features |
| [linucb_explained.md](linucb_explained.md) | The LinUCB math, variable by variable |
| [reward_design.md](reward_design.md) | How events become rewards without corruption |
| [database_design.md](database_design.md) | Tables, keys, indexes, ER diagram |
| [api_documentation.md](api_documentation.md) | Every endpoint, request and response |
| [evaluation_methodology.md](evaluation_methodology.md) | How we prove the algorithm works |
| [presentation_guide.md](presentation_guide.md) | Demo script for the judges |

## Reading paths

**Judge / reviewer:** `system_design.md` -> `evaluation_methodology.md` -> `presentation_guide.md`

**Engineer joining the build:** root `DEVELOPMENT_GUIDE.md` -> `ml_architecture.md`
-> `linucb_explained.md` -> `database_design.md` -> `api_documentation.md`

**ML-focused reader:** `linucb_explained.md` -> `reward_design.md`
-> `evaluation_methodology.md`

## Conventions used in these docs

- `x` is a context vector (one row), `A` is a matrix, `b` is a vector.
- "candidate" = a course returned by retrieval and eligible for ranking.
- "impression" = a recommendation actually shown to a user.
- "reward" = a scalar derived from one interaction event.
- All numeric examples are **simulated**, never production metrics.
