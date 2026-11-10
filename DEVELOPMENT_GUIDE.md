# Development Guide

A step-by-step path from an empty folder to a working, testable prototype.
Each step says **what to build**, **why**, and **how to check it works**.

> Read this together with [`PROJECT_ROADMAP.md`](PROJECT_ROADMAP.md) (order and
> priorities) and [`ARCHITECTURE.md`](ARCHITECTURE.md) (how parts fit).

---

## 0. Prerequisites

- Python 3.11+
- Node.js 20+ and npm
- Docker Desktop (for PostgreSQL) — optional but recommended
- Basic comfort with Python, NumPy, and React

Verify:

```bash
python --version
node --version
docker --version
```

## 1. Environment setup

```bash
# from repo root
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
cp .env.example .env        # then edit values
```

Start the database:

```bash
docker compose up -d db
```

Check: `docker compose ps` shows the DB healthy.

## 2. Backend skeleton

Build in this order — each file only depends on the ones above it:

1. `backend/app/core/config.py` — typed settings from env.
2. `backend/app/database/connection.py` + `base.py` — engine, session, Base.
3. `backend/app/models/*` — tables.
4. Alembic init + first migration.
5. `backend/app/main.py` — app factory, router mounting, health check.

Check:

```bash
uvicorn app.main:app --reload --app-dir backend
# open http://127.0.0.1:8000/docs
curl http://127.0.0.1:8000/health
```

**Why this order:** settings feed the DB, the DB feeds models, models feed schemas,
schemas feed routes. Building in reverse creates circular fixes.

## 3. ML foundation (do this before HTTP routes)

Pure Python/NumPy modules, no FastAPI, no database. This keeps them unit-testable
and reusable by both the API and the experiments.

### 3.1 Course data

- Put the catalogue in `data/courses/courses.csv`.
- Load, validate (no nulls in required fields), clean, normalize in
  `ml/feature_engineering.py`.
- Check: a tiny script prints `n_courses`, null counts, and category distribution.

### 3.2 Synthetic users

- `experiments/synthetic_users.py` generates users with **hidden** preference
  vectors over categories.
- The simulator knows preferences; the algorithm never receives them.
- Check: with seed 42, two runs produce identical users.

### 3.3 Retrieval

- `ml/tfidf_retriever.py`: fit TF-IDF on course text, cosine similarity, top-50.
- `ml/embedding_retriever.py`: same interface, sentence embeddings.
- Check: a unit test asserts both return at most 50 items, sorted by score,
  and that an obviously relevant query surfaces relevant categories.

### 3.4 LinUCB

- `ml/linucb.py`: `A`, `b`, `theta`, `score`, `select`, `update`, `save`, `load`.
- Check (`tests/test_linucb.py`):
  - `A` stays symmetric positive definite after many updates.
  - `score` is finite for large feature vectors.
  - the same context repeated with the same reward converges (theta stabilizes).
  - save -> load -> identical predictions.

### 3.5 Reward engine

- `ml/reward_engine.py`: `click=+1`, `inspect=+1`, `purchase=+10`, `no_interaction=0`,
  weights from settings.
- Check: no event type can be counted twice; unknown types raise.

## 4. Experiments (prove it works before wiring the API)

```bash
python scripts/run_experiments.py --users 200 --rounds 50 --seeds 5
```

Implement in `experiments/`:

1. `environment.py` — one round: retrieval -> policy -> simulated feedback -> reward.
2. `random_baseline.py`, `popularity_baseline.py`, `bandit_experiment.py` — same
   candidate sets and same simulator.
3. `metrics.py` — cumulative reward/regret, CTR, conversion, precision/recall/NDCG@K.
4. `plots.py` — save PNGs to `experiments/outputs/`.

Check: three policies produce distinct learning curves; LinUCB beats random on
cumulative reward across seeds; popularity has no future leakage.

## 5. Backend API

Implement routes in `api/` as thin wrappers over `services/`:

- `users.py` — register, profile.
- `courses.py` — list, detail.
- `recommendations.py` — GET by user (retrieval + LinUCB).
- `interactions.py` — impression, click, inspect, purchase.
- `analytics.py` — overview, comparison, regret.

Rules:

- Every response is a Pydantic schema.
- Errors return the right status code, never a 200 with an error body.
- Impressions are written at recommendation time.

Check: `pytest backend/tests` passes; `/docs` shows every endpoint.

## 6. Frontend

```bash
cd frontend
npm install
npm run dev
```

Build order:

1. `types/` — mirror the API schemas.
2. `services/api.ts` — typed fetch client, single base URL from env.
3. `pages/Onboarding.tsx` — collects the profile.
4. `pages/Feed.tsx` — course cards + reason + actions.
5. `pages/Analytics.tsx` — Recharts from `/analytics/*`.

Check: onboarding posts a real profile, the feed loads from the API (not mocks),
clicking a card posts an interaction and the analytics counters move.

## 7. Integration checklist

- [ ] New user -> onboarding -> personalized feed with reasons.
- [ ] Click / inspect / purchase recorded exactly once each.
- [ ] Analytics reflect recorded events.
- [ ] Impressions match the number of displayed cards.
- [ ] Bandit state persists across restarts.
- [ ] `pytest` green; `npm run build` green.
- [ ] Demo runs from a clean clone via `docker compose up`.

## 8. Conventions

- Type hints on all public functions; docstrings on all modules.
- No business logic in routes; no SQL in `ml/`.
- Config only through `core/config.py`, never `os.environ` scattered around.
- One responsibility per module; if a file needs "and" to describe it, split it.
- Commit messages: `feat:`, `fix:`, `docs:`, `test:`, `exp:`.

## 9. How to test each layer

| Layer | Command | What it proves |
|---|---|---|
| ML units | `pytest backend/tests/test_linucb.py` | math is correct |
| Retrieval | `pytest backend/tests/test_retrieval.py` | candidates sensible |
| Rewards | `pytest backend/tests/test_rewards.py` | no double counting |
| API | `pytest backend/tests/test_api.py` | contracts + status codes |
| Experiments | `python scripts/run_experiments.py` | algorithm beats baselines |
| Frontend | `npm run build` + manual | UI wired to API |

## 10. What to learn, in order

1. Cosine similarity and TF-IDF (start here — it is simple and visual).
2. Why bandits exist: exploration vs exploitation.
3. Ridge regression, because LinUCB is ridge regression plus an uncertainty bonus.
4. Matrix inverse and why numerical stability matters.
5. Evaluation: why a single seed lies, and why confidence intervals matter.
6. FastAPI dependency injection and Pydantic validation.
7. SQLAlchemy sessions and migrations.
8. React data fetching and state for a small app.
