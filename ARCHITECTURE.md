# Architecture

This document explains **what exists, what each part is responsible for, and how
they communicate**. Implementation detail lives in [`docs/`](docs/).

---

## 1. Architectural style

A **modular monolith**:

- One Python deployable (FastAPI).
- Clear internal boundaries: `api` -> `services` -> `ml` / `models`.
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
| `ml/` | Pure algorithms: features, retrieval, LinUCB, reward, persistence | Know about HTTP or ORM sessions |
| `models/` | SQLAlchemy tables, relationships, indexes | Contain business rules |
| `schemas/` | Pydantic request/response contracts | Contain logic |
| `database/` | Engine, session factory, declarative base | Business logic |
| `core/` | Settings, constants, logging | Domain logic |
| `experiments/` | Offline simulation, baselines, metrics, plots | Serve HTTP |
| `frontend/` | UX: onboarding, feed, analytics, API client | Compute ML |

**Rule of thumb:** if it imports FastAPI inside `ml/`, the boundary is broken. If it
opens a DB session inside `ml/`, the boundary is broken.

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
        |-- 2. build user feature vector (ml/feature_engineering.py)
        |-- 3. retrieval: top-50 candidates (ml/tfidf_retriever.py | embedding_retriever.py)
        |-- 4. build context vectors x for (user, course) pairs
        |-- 5. LinUCB score + UCB bonus + argmax (ml/linucb.py)
        |-- 6. persist Recommendation rows (models/recommendation.py)
        |-- 7. persist Impression rows (models: impressions)
        v
api response: ranked list + reason per course
```

Steps 6 and 7 are what make CTR and conversion correct later: the denominator
(impressions) is recorded at the moment of display, not reconstructed afterwards.

## 4. Request lifecycle: "record a purchase"

```
POST /api/interactions/purchase
        |
        v
api/interactions.py  ->  services/interaction_service.py
                                |
                                |-- 1. verify impression exists for (user, course)
                                |-- 2. reward = reward_engine.compute("purchase")   # +10
                                |-- 3. persist Interaction(event_type, reward)
                                |-- 4. map interaction -> bandit update:
                                |       linucb.update(context, reward)
                                |-- 5. persist BanditState (version, params)
                                v
                         200 OK
```

Important: the purchase does **not** retroactively add click rewards. Each event is
logged once, independently. Rewards are computed by `reward_engine.py`, never inside
`linucb.py`. See [`docs/reward_design.md`](docs/reward_design.md).

## 5. Where the ML actually lives

```
ml/
├── feature_engineering.py   # user/course/context -> numeric vectors
├── tfidf_retriever.py       # corpus -> TF-IDF matrix -> top-k by cosine
├── embedding_retriever.py   # corpus -> sentence embeddings -> top-k by cosine
├── linucb.py                # A, b, theta, UCB score, update, save/load
├── reward_engine.py         # event_type -> reward, weights configurable
└── model_persistence.py     # joblib/npz artifacts, versioning
```

Retrieval answers **"which 50 courses are relevant?"**. LinUCB answers **"which of
these 50 should we show first to this user right now?"**. These are separate
problems and must not be merged.

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

## 7. Data model overview

```
users 1---* interactions *---1 courses
users 1---* recommendations *---1 courses
users 1---* impressions *---1 courses
recommendations 1---* impressions
bandit_state (global, versioned)
```

Full DDL, constraints and indexes: [`docs/database_design.md`](docs/database_design.md).

## 8. Key decisions and why

| Decision | Reason | Trade-off accepted |
|---|---|---|
| Modular monolith | team size, scope | one deploy unit |
| TF-IDF first, embeddings second | TF-IDF is deterministic and free | embeddings add dependency weight |
| No FAISS | ~hundreds of courses, exact cosine is fine | no ANN speedup (unneeded) |
| LinUCB from scratch | explainability to judges, learning value | must handle numerical stability ourselves |
| Shared LinUCB model | simpler, enough data | no per-segment models yet |
| No LLM in loop | not required, adds latency/cost/nondeterminism | NL profile parsing is a documented extension |
| Synthetic simulator | reproducible evaluation | results are simulated, not real |

## 9. Critical risks

1. **Data leakage in popularity baseline** — popularity must be computed from the
   past window only, never from the evaluation window.
2. **Reward double counting** — a purchase must not also add a click reward.
3. **Impression denominator** — without impressions at display time, CTR and
   conversion become meaningless.
4. **LinUCB numerical instability** — `A` must stay positive definite; solve with a
   stable method and a small ridge term, never a naive inverse of a singular matrix.
5. **Feature scale mismatch** — unnormalized price/duration dominate the dot product;
   normalize all numeric features to a comparable range.
6. **Overclaiming results** — simulated lift is not real lift; state this everywhere.

Details and mitigations: [`PROJECT_ROADMAP.md`](PROJECT_ROADMAP.md#risk-register).
