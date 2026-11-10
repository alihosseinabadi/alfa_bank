# Project Roadmap

Priorities, phases and risks. Ordered so that **the ML story is proven before the
product is polished** — judges reward a working, explainable algorithm more than a
pretty shell around an unvalidated one.

---

## Guiding priority

```
1. Correct recommendation algorithm + honest evaluation   (must have)
2. Working end-to-end user flow                            (must have)
3. Clear analytics that prove the algorithm                (must have)
4. Polish, animations, extra screens                       (nice to have)
```

If time runs out, cut from the bottom, never from the top.

## Phase overview

| Phase | Goal | Exit criterion |
|---|---|---|
| 0 | Architecture + docs | This repository layer exists |
| 1 | Foundation | API boots, DB connects, env documented |
| 2 | ML core | Retrieval + LinUCB + rewards unit-tested |
| 3 | Experiments | LinUCB beats baselines across seeds |
| 4 | Backend | All endpoints implemented and tested |
| 5 | Frontend | Three screens wired to the API |
| 6 | Delivery | Demo reproducible from a clean clone |

## Phase 0 — Architecture (done)

- Root docs: README, ARCHITECTURE, DEVELOPMENT_GUIDE, ROADMAP.
- `docs/` deep dives.
- Directory READMEs describing every planned file.

## Phase 1 — Foundation

**Deliverables**
- `backend/app/core/config.py` with typed settings.
- `backend/app/database/` engine + session + Base.
- `backend/requirements.txt`, `.env.example`, `docker-compose.yml`.
- `backend/app/main.py` with `/health`.

**Definition of done:** `uvicorn` runs, `/health` returns 200, DB connection checked.

## Phase 2 — ML core

**Deliverables**
- `data/courses/courses.csv` (validated).
- `ml/feature_engineering.py`.
- `ml/tfidf_retriever.py` and `ml/embedding_retriever.py` (same interface).
- `ml/linucb.py` (shared model, persistence).
- `ml/reward_engine.py`.
- `experiments/synthetic_users.py`.

**Definition of done:** `pytest` green for LinUCB, retrieval, rewards. Simulator is
seed-reproducible and preferences are never passed to the algorithm.

**Highest-risk phase.** Budget the most time here.

## Phase 3 — Experiments

**Deliverables**
- `experiments/environment.py`, three policies, `metrics.py`, `plots.py`.
- `scripts/run_experiments.py` reporting means and confidence intervals over seeds.

**Definition of done:** A results table and 4+ plots show LinUCB vs Random vs Popular
on cumulative reward, regret, CTR, conversion, NDCG@K. Popularity uses only past data.

## Phase 4 — Backend API

**Deliverables**
- Models, schemas, Alembic migration.
- Routes: users, courses, recommendations, interactions, analytics.
- Services wiring retrieval + LinUCB + rewards.

**Definition of done:** all endpoints in `/docs`; impression logging verified;
`tests/test_api.py` green.

## Phase 5 — Frontend

**Deliverables**
- Onboarding form.
- Personalized feed with reason + actions.
- Analytics dashboard with charts.

**Definition of done:** UI reads/writes the real API; no hardcoded data.

## Phase 6 — Delivery

**Deliverables**
- `docker-compose up` runs DB + API (+ UI build served).
- Seed script loads catalogue.
- Demo script rehearsed and timed.
- Presentation following `docs/presentation_guide.md`.

**Definition of done:** a clean clone reaches a working demo in under 5 minutes.

---

## Risk register

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | Popularity baseline leaks future data | Invalid results, judge distrust | Compute from prior window only; test explicitly |
| 2 | Purchase double-counted as click | Inflated reward, skew | Reward computed once per event; unit test |
| 3 | Missing impressions | CTR/conversion wrong | Insert impression at display time |
| 4 | LinUCB `A` singular / unstable | NaN scores | Ridge term, stable solve, assert positive definite |
| 5 | Unnormalized features | Dot product dominated by price | Min-max / z-score numeric features |
| 6 | Single-seed conclusions | Overclaiming | 5+ seeds, report mean + CI |
| 7 | Real vs simulated confusion | Credibility loss | Label every chart "simulated" |
| 8 | Scope creep (LLM, auth, payments) | Core unfinished | Hard no; documented extensions only |
| 9 | Dataset too small for embeddings to help | Wasted time | Compare TF-IDF vs embeddings empirically, keep the better |
| 10 | Time lost on infra | Demo missing | Docker first, then features |

## Decision log

| Decision | Alternatives | Chosen because |
|---|---|---|
| Shared LinUCB | per-category bandits | data volume too low for many models |
| TF-IDF primary | embeddings primary | deterministic, no model download, fast |
| Synthetic simulator | real logs | no real traffic in a hackathon |
| Modular monolith | microservices | one team, one domain, one deploy |
| No LLM | LLM profile parsing | not required; adds cost/latency/nondeterminism |

## Definition of "demo-ready"

- [ ] Clean clone -> `docker compose up` -> API healthy.
- [ ] Seed data loads.
- [ ] Onboarding produces a personalized feed.
- [ ] Interactions update analytics live.
- [ ] Experiment plots regenerated from the repo.
- [ ] Presentation deck + spoken script ready.
