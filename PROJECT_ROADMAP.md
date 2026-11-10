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
| 2 | ML core | Features + retrieval + LinUCB + rewards unit-tested |
| 3 | Experiments | LinUCB beats baselines across 10 seeds |
| 4 | Backend | All endpoints implemented and tested |
| 5 | Frontend | Three screens wired to the API |
| 6 | Delivery | Demo reproducible from a clean clone |

## Phase 0 — Architecture (done)

- Root docs: README, ARCHITECTURE, DEVELOPMENT_GUIDE, ROADMAP.
- `docs/` deep dives, including the feature contract and data provenance.
- Directory READMEs describing every planned file.

## Phase 1 — Foundation

**Deliverables**
- `backend/app/core/config.py` with typed settings (including reward weights,
  `alpha`, `retrieval_k`, `purchase_attribution_days`).
- `backend/app/database/` engine + session + Base.
- `backend/requirements.txt`, `.env.example`, `docker-compose.yml`.
- `backend/app/main.py` with `/health`.

**Definition of done:** `uvicorn` runs, `/health` returns 200, DB connection checked.

## Phase 2 — ML core

**Deliverables**
- `data/courses/courses.csv` validated (including `source`).
- `ml/feature_engineering.py` implementing `docs/feature_engineering.md`
  (`FEATURE_LAYOUT`, `FEATURE_VERSION`, `d = 4K + 15`).
- `ml/tfidf_retriever.py` and `ml/embedding_retriever.py` (same interface).
- `ml/linucb.py` (shared model, persistence, `feature_version` check).
- `ml/reward_engine.py` (configurable weights, no event semantics in LinUCB).
- `experiments/synthetic_users.py`.

**Definition of done:** `pytest` green for features, LinUCB, retrieval, rewards and
data validation. Simulator is seed-reproducible; preferences are never passed to the
algorithm; a test asserts the feature builder cannot receive them.

**Highest-risk phase.** Budget the most time here.

## Phase 3 — Experiments

**Deliverables**
- `experiments/environment.py`, three policies, `metrics.py`, `plots.py`.
- `scripts/run_experiments.py` with `--seeds 10` default, reporting means and 95%
  confidence intervals across seeds.

**Definition of done:** A results table and 7 plots show LinUCB vs Random vs Popular
on cumulative reward, regret, CTR, inspection rate, conversion, exploration share and
NDCG@K. Popularity uses only past data. `test_evaluation.py` and `test_leakage.py`
are green.

## Phase 4 — Backend API

**Deliverables**
- Models (including canonical `recommendation_impressions`), schemas, Alembic migration.
- Routes: users, courses, recommendations, interactions, analytics.
- Services wiring retrieval + LinUCB + rewards with impression-based attribution.

**Definition of done:** all endpoints in `/docs`; impression logging verified;
duplicate-event and stale-attribution paths return 409; `tests/test_api.py` green.

## Phase 5 — Frontend

**Deliverables**
- Onboarding form (including budget sensitivity).
- Personalized feed with reason + actions.
- Analytics dashboard with charts (three separate funnel metrics).

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
| 1 | Popularity baseline leaks future data | Invalid results, judge distrust | window query `shown_at < window_start`; `test_leakage.py` |
| 2 | Purchase double-counted as click | Inflated reward, skew | unique `(impression_id, event_type)`; purchase never expands; unit tests |
| 3 | Duplicate click/purchase events | Inflated metrics | unique constraints + service idempotency |
| 4 | Missing impressions | CTR/conversion meaningless | one `recommendation_impressions` row per displayed course, written in-transaction |
| 5 | Hidden preferences leak into features | Fake lift | observable-only feature builder; signature + import tests |
| 6 | LinUCB `A` singular / unstable | NaN scores | ridge term, `solve`, symmetrize, finiteness checks |
| 7 | Unnormalized features | Dot product dominated by price | clip all features to `[0,1]` |
| 8 | Too few seeds | Overclaiming | ≥10 seeds, 95% CI across seeds |
| 9 | Simulated vs real confusion | Credibility loss | provenance doc, every chart labelled "simulated" |
| 10 | Scope creep (LLM, auth, payments) | Core unfinished | hard no; documented extensions only |
| 11 | Dataset mistaken for real Alfa-Kurs data | Ethical/credibility issue | `source=synthetic` column, provenance doc |
| 12 | Time lost on infra | Demo missing | Docker first, then features |

## Decision log

| Decision | Alternatives | Chosen because |
|---|---|---|
| Single `recommendation_impressions` table | separate recommendations + impressions | no duplicated display record, unambiguous attribution |
| Shared LinUCB + interaction features | per-category bandits | data volume too low for many models; interaction block personalizes |
| Remove device/hour/session | keep as context | no data source, no measured benefit |
| TF-IDF primary | embeddings primary | deterministic, no model download, fast |
| Synthetic simulator | real logs | no real traffic in a hackathon |
| Modular monolith | microservices | one team, one domain, one deploy |
| No LLM | LLM profile parsing | not required; adds cost/latency/nondeterminism |

## Definition of "demo-ready"

- [ ] Clean clone → `docker compose up` → API healthy.
- [ ] Seed data loads (catalogue marked synthetic).
- [ ] Onboarding produces a personalized feed.
- [ ] Interactions update analytics live; duplicate events are rejected.
- [ ] 10-seed experiment plots regenerated from the repo.
- [ ] Presentation deck + spoken script ready.
