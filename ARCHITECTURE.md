# Architecture

This document explains **what exists, what each part is responsible for, and how
they communicate**. Implementation detail lives in [`docs/`](docs/).

---

## 1. Architectural style

A **modular monolith**:

- One Python deployable (FastAPI).
- Clear internal boundaries: `api` → `services` → `ml` / `models`.
- No microservices, no message broker, no service mesh.

Why: hackathon scope, a small team, and a single domain. Microservices would add
network boundaries without adding value. Internal module boundaries keep the code
testable and let the ML layer evolve independently of HTTP concerns.

```
                 +-----------------------------------------+
  React SPA ---> |                FastAPI                  |
                 |                                         |
                 |  api/  (HTTP, validation, status codes)  |
                 |    |                                    |
                 |    v                                    |
                 |  services/ (orchestration, transactions)|
                 |    |               |                    |
                 |    v               v                    |
                 |  ml/            models/  (SQLAlchemy)    |
                 |  retrieval      database/ (sessions)    |
                 |  LinUCB                                 |
                 |  rewards                                |
                 +-----------------------------------------+
                            |                    |
                            v                    v
                     PostgreSQL            data/ + artifacts/
```

## 2. Component responsibilities

| Component | Responsibility | Must NOT do |
|---|---|---|
| `api/` | Parse requests, validate with Pydantic, call services, map errors to HTTP | Contain ML math or SQL |
| `services/` | Business workflows, transaction boundaries, combine retrieval + bandit | Talk directly to HTTP or render |
| `ml/` | Pure algorithms: features, retrieval, LinUCB, reward, persistence | Know about HTTP, ORM sessions, or `experiments/` |
| `models/` | SQLAlchemy tables, relationships, indexes | Contain business rules |
| `schemas/` | Pydantic request/response contracts | Contain logic |
| `database/` | Engine, session factory, declarative base | Business logic |
| `core/` | Settings, constants, logging | Domain logic |
| `experiments/` | Offline simulation, baselines, metrics, plots | Serve HTTP |
| `frontend/` | UX: onboarding, feed, analytics, API client | Compute ML |

**Rule of thumb:** if it imports FastAPI inside `ml/`, the boundary is broken. If it
opens a DB session inside `ml/`, the boundary is broken. If `ml/` imports
`experiments/`, the separation between policy and simulator is broken.

## 3. Request lifecycle: "get recommendations for a user"

```
GET /api/recommendations/{user_id}
        |
        v
api/recommendations.py
        |  validate path/query, load user via service
        v
services/recommendation_service.py
        |
        |-- 1. load user profile (models/user.py)
        |-- 2. build user feature block (ml/feature_engineering.py)
        |-- 3. retrieval: top-50 candidates (ml/tfidf_retriever.py | embedding_retriever.py)
        |-- 4. build context vectors x = [user | course | interaction] per candidate
        |-- 5. LinUCB score + UCB bonus + rank (ml/linucb.py)
        |-- 6. persist ONE slate of recommendation_impressions rows
        |       (slate_id, position, retrieval_score, bandit_score, algorithm,
        |        model_version, shown_at)
        v
api response: ranked list + reason + impression_id per course
```

Step 6 is what make CTR and conversion correct later: the denominator is recorded at
the moment of display, not reconstructed afterwards. There is **no separate
impressions table** — the impression *is* the recommendation record.

## 4. Request lifecycle: "record a purchase"

```
POST /api/interactions/purchase
        |
        v
api/interactions.py  ->  services/interaction_service.py
                                |
                                |-- 1. resolve impression_id (given or most recent
                                |       for user+course, within 7 days)
                                |-- 2. reward = reward_engine.compute("purchase")   # +10
                                |-- 3. persist Interaction(impression_id, event_type, reward)
                                |       unique (impression_id, event_type) blocks duplicates
                                |-- 4. linucb.update(context_of_that_impression, reward)
                                |-- 5. persist BanditState (version, params)
                                v
                         201 OK
```

Important: the purchase does **not** retroactively add click rewards. Each event is
logged once, independently, and capped per impression. Rewards are computed by
`reward_engine.py`, never inside `linucb.py`. See
[`docs/reward_design.md`](docs/reward_design.md).

## 5. Where the ML actually lives

```
ml/
├── feature_engineering.py   # validate courses; user/course/interaction -> x
├── tfidf_retriever.py       # corpus -> TF-IDF matrix -> top-k by cosine
├── embedding_retriever.py   # corpus -> sentence embeddings -> top-k by cosine
├── linucb.py                # A, b, theta, UCB score, update, save/load
├── reward_engine.py         # event_type -> reward, weights configurable
└── model_persistence.py     # joblib/npz artifacts, feature_version
```

Retrieval answers **"which 50 courses are relevant?"**. LinUCB answers **"which of
these 50 should we show first to this user right now?"**. These are separate
problems and must not be merged.

The context vector is `x = [user | course | interaction]` with
`d = 4K + 15`. The interaction block (`interest × category`, match, experience–difficulty
fit, goal–skill overlap, free and price interactions) is what makes a shared model
personalize. Full contract: [`docs/feature_engineering.md`](docs/feature_engineering.md).

## 6. Offline experiments vs online serving

They share the same `ml/` modules, which is the point:

| | Online (API) | Offline (experiments/) |
|---|---|---|
| User source | PostgreSQL | synthetic simulator |
| Candidate source | retriever over course table | retriever over course data |
| Decision | LinUCB argmax | LinUCB / Random / Popular |
| Feedback | real clicks/purchases | simulated with hidden preferences |
| Output | recommendations | metrics + plots |

Because both paths call the same `linucb.py` and `reward_engine.py`, a result in the
simulator is a meaningful statement about the serving code, not about a rewrite.

The simulator's hidden preferences and oracle live in `experiments/` only. `ml/`
cannot import them, and a test asserts that.

## 7. Data model overview

```
users 1---* recommendation_impressions *---1 courses
                      |
                      | 1
                      |*
              interactions            (impression_id is the attribution key)
bandit_state (global, versioned)
```

One row in `recommendation_impressions` = one course shown at one position in one
slate. Full DDL, constraints and indexes:
[`docs/database_design.md`](docs/database_design.md).

## 8. Key decisions and why

| Decision | Reason | Trade-off accepted |
|---|---|---|
| Modular monolith | team size, scope | one deploy unit |
| TF-IDF first, embeddings second | TF-IDF is deterministic and free | embeddings add dependency weight |
| No FAISS | ~hundreds of courses, exact cosine is fine | no ANN speedup (unneeded) |
| LinUCB from scratch | explainability to judges, learning value | must handle numerical stability ourselves |
| Shared LinUCB model | data per user too small | no per-segment models yet |
| Interaction features | shared model still personalizes | slightly larger `d` |
| No device/hour/session | no data source, no measured benefit | less context |
| No LLM in loop | not required, adds latency/cost/nondeterminism | NL profile parsing is a documented extension |
| Synthetic simulator | reproducible evaluation | results are simulated, not real |

## 9. Critical risks

1. **Data leakage in popularity baseline** — popularity must be computed from the
   past window only, never from the evaluation window. Tested in `test_leakage.py`.
2. **Reward double counting** — a purchase must not also add a click reward; the
   unique `(impression_id, event_type)` constraint and tests enforce it.
3. **Impression denominator** — without impression rows at display time, CTR,
   inspection rate and conversion become meaningless.
4. **LinUCB numerical instability** — `A` must stay positive definite; use a ridge
   term and `solve`, never a naive inverse.
5. **Feature scale mismatch** — unnormalized price/duration dominate the dot product;
   clip everything to `[0,1]`.
6. **Hidden preference leakage into features** — would make evaluation fake. The
   feature builder accepts observable fields only.
7. **Overclaiming results** — simulated lift is not real lift; state this everywhere.

Details and mitigations: [`PROJECT_ROADMAP.md`](PROJECT_ROADMAP.md#risk-register).
