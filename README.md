# Alfa-Kurs — adaptive learning recommendations

**Кратко по-русски.** Alfa-Kurs подбирает учебные материалы предпринимателям по
их задаче: гибридный поиск BM25 + плотные векторы → признаки →
prior-ранжирование → LinUCB → слэйт → события показов и кликов. В Docker-демо
для жюри каталог **синтетический**: он генерируется скриптом внутри стека, а
рекомендации выдаёт настоящий конвейер BM25 + dense → prior → LinUCB, и UI
помечает такой каталог как демонстрационный. Реальный каталог организатора
приватен и в репозиторий не входит. Конверсия, продажи и эффект обучения на
живых данных **не измерялись**.

A hackathon project for the Alfa-Bank Web/AI hackathon, track
"Personalization of education for entrepreneurs". The product is a task-first
recommender for the Alfa-Kurs catalogue: a user describes a business task, gets
ranked learning materials with explanations, and the system records impressions,
visibility and clicks that feed a reward worker.

**Presentation:** [`presentation/Alfa-Kurs-product-2026-11-17.pdf`](presentation/Alfa-Kurs-product-2026-11-17.pdf)
— the 9-page product walkthrough in Russian.
**Verification record:** [`docs/submission-report.md`](docs/submission-report.md).

---

## 1. What it is

Profile / task → hybrid retrieval: BM25 + dense vectors (top-50) → feature
builder → prior ranking → LinUCB → slate shaping → explanations → UI. The same
path records canonical impressions and interactions; a background worker
projects delayed rewards and updates the shared LinUCB model.

```
 task / profile
      │
      ▼
 hybrid retrieval ──► candidate materials (top-50)
   BM25 + dense vectors, 60/40 score fusion
      │
      ▼
 feature vector (user | course | interaction)
      │
      ▼
 prior ranking ──► LinUCB score (exploit + explore)
      │
      ▼
 slate: eligibility, filters, diversity, positions
      │
      ▼
 UI cards + "why recommended"
      │
      ▼
 impression / visibility / click / purchase events
      │
      ▼
 reward worker ──► model update
```

Two PostgreSQL databases are used: the **product** database (users, courses,
interactions) and the isolated **events** database (impressions, decisions,
reward ledger). They are deliberately separate.

What is actually implemented: FastAPI backend, React/Vite frontend, BM25 and
TF-IDF retrieval, a real dense-vector channel (LSA over the Russian analyzer,
persisted as a versioned dataset), normalized 60/40 BM25 + dense fusion, the 22-feature
builder, deterministic prior ranking, shared LinUCB, slate policy, internal event
service, reward ledger and replay, anonymous signed sessions with CSRF, two
Alembic migration chains, and this Docker demo stack. What is not: real organizer
data, live payments, external material opening, live analytics, a private E5
model, and a measured business effect.

---

## 2. Quick start

There are two ways in; neither needs private data.

### Option A — Docker, one command (the judge path)

Requires Docker Desktop with Compose v2.

```bash
cp .env.example .env
docker compose up --build
```

Open **http://localhost:5173**. The API health endpoint is
**http://localhost:8000/health** and the nginx proxy also exposes
**http://localhost:5173/health**.

- First build: roughly 3–6 minutes depending on network (Python and npm
  downloads). Later starts are much faster.
- Stop: `docker compose down`. Reset the databases and start clean:
  `docker compose down -v && docker compose up --build`.
- The stack builds a **synthetic demo catalogue** inside a shared volume
  (`scripts/build_demo_catalog.py`) and runs the **real ML path** on it: hybrid
  BM25 + dense retrieval → prior ranking → LinUCB → slate. The dense channel is a
  TF-IDF → truncated-SVD (LSA) model trained on each public chunk plus the
  material's description, topics and tags, and saved as a checksummed, versioned
  vector dataset (`lsa-tfidf-svd-v2`, 64 dimensions, 118 rows); the API loads
  that dataset instead of retraining on start. The
  tracked source is `data/courses/courses.csv` (12 courses); the same rows are
  seeded into the product `courses` table by `scripts/seed_courses.py`, so
  `/api/v1/courses` returns real database rows, not frontend fixtures. Six short
  articles, one checklist document and one webinar are added to the ML bundle,
  giving 20 indexed materials and 118 public chunks. The UI calls the API, so
  cards come from that pipeline, and both the dashboard and the feed carry a
  visible «синтетический каталог» notice. The CSV is baked into the backend image
  as source; the bundle, index and vector dataset are built at container start.
- The API, both databases, migrations, sessions, event recording and the reward
  worker are real and start as part of the same stack.
- If `docker` is not installed, install Docker Desktop first
  (`winget install Docker.DockerDesktop` on Windows) and start it once. The
  command cannot work without Docker.

If port 5173 or 8000 is busy, set `FRONTEND_PORT` / `API_PORT` in `.env`.

> **Status of this snapshot.** These two commands were executed successfully on
> 2026-11-16: both images built, `migrate` exited 0, `db` and `api` reported
> healthy, `worker` and `frontend` stayed up, the UI answered on
> `http://localhost:5173`, `/health` answered `{"status":"ok"}` and the nginx
> `/api` proxy created a user (`HTTP 201`). Exact output:
> [`docs/submission-report.md`](docs/submission-report.md).

### Option B — UI demo without Docker (no database)

On Windows, double-click **`start-demo.cmd`**, or run it from a terminal:

```bat
start-demo.cmd
```

It installs `frontend/node_modules` on the first run, starts Vite in demo mode on
**http://127.0.0.1:5173** and opens the browser once the page answers. Add
`--no-open` to skip the browser, or `--port 5174` to change the port.

macOS / Linux:

```bash
npm --prefix frontend ci
VITE_RECOMMENDATIONS_SOURCE=demo npm --prefix frontend run dev
```

This path is client-side only: it shows the labelled demo cards but does not
start the API, the databases or the worker.

### Troubleshooting

- `npm : ... cannot be loaded because running scripts is disabled` — PowerShell
  blocks `npm.ps1` on this machine. Use `npm.cmd` instead of `npm`, or just run
  `start-demo.cmd`.
- The page does not open — try **http://127.0.0.1:5173** explicitly. Some setups
  resolve `localhost` to IPv6 while the dev server listens on IPv4; also check
  that nothing else occupies port 5173.
- Port already in use — `start-demo.cmd --port 5174`, or set `FRONTEND_PORT` in
  `.env` for Docker.

---

## 3. How to test the main features

Use the UI at **http://127.0.0.1:5173** (or the port you chose). The first five
steps work in both quick-start options; registration and event checks need the
API (Option A, or the manual backend in section 6).

1. **Entry.** `/auth` is a split Alfa-style screen with sign-up, sign-in and
   «Войти в демо без регистрации». A new account always starts a clean profile;
   nothing from a previous demo profile is reused.
2. **Profile analysis (8 steps).** Choose the main task (or type your own), role,
   sphere and stage, experience, up to four interests, weekly hours and preferred
   format, the main constraint, and a free-text description. The next screen is
   a profile analysis: archetype, readiness ring, pace and a short list of «Что
   профилю действительно нужно». This analysis is deterministic demo logic, not
   a trained model.
3. **Dashboard.** `/dashboard` shows the course of the day from the ML-ranked
   catalogue (a course format is preferred), profile readiness, a 14-day
   synthetic progress chart, a monthly activity calendar, a four-week roadmap and
   the daily question. Answering the question stores an insight in the local
   profile and adds that topic as a compact term to the next ranking query — not
   the whole sentence, so BM25 stays usable.
4. **Full ranked catalogue.** `/feed` calls the read-only
   `POST /api/v1/catalogue/rank` endpoint and shows all 20 synthetic materials.
   The endpoint fuses BM25 with dense-vector cosine by scaling each channel to
   its best score and combining them 60/40, then applies
   the same prior ranker the serving path uses. Items found by the hybrid keep
   their real fit score, ML rank and dense cosine. Items outside the retrieval
   slate are shown lower with a clearly labelled `~profile fit` heuristic
   («оценка профиля · не ML»); they are never presented as model scores. Fit
   score is a relative match within this request, not a purchase probability.
5. **Coach.** `/coach` is a chat over the same ranking pipeline. The frontend
   sends the user's raw wording; the backend analyzer normalises case and `ё`,
   removes conversational stop words, applies Russian Snowball stemming and a
   deterministic business thesaurus (наём/нанять, клиент/заявка,
   конкуренты/маркетинг, себестоимость/юнит-экономика, …), then fuses BM25 with
   the dense channel. No client-side keyword expansion is used. The reply meta
   reports the algorithm, dense model/dimensions and LinUCB state (`cold`,
   `warm` with observation count, or `unavailable`). A query with no retrieval
   match returns a clarification and does **not** overwrite the profile goal or
   show 0% items as picks.
6. **Analytics.** `/analytics` is a customer-facing learning dashboard: activity
   over 14 days, a topic radar built from the profile and daily answers, the
   collection, the declared pace versus the actual step, and next actions. All
   numbers come from local demo actions and are labelled synthetic. The static
   NDCG@10 panel from `docs/quality_stage56.md` is kept behind a closed
   «Для инженеров» disclosure, not mixed into client metrics.
7. **Profile.** `/profile` edits the same fields, interests and password-free
   demo account, shows the roadmap, completed courses, saved items and a reset
   action. There is one local profile: «Анкета» updates it instead of creating a
   second server record. The catalogue preview is read-only: it records no
   decision and no event.
8. **State and backend.** Refresh the page: the account, answers, daily answer
   and course progress are restored from browser storage. «Выйти» clears them.
   The API, databases and worker run even in demo mode:

   ```bash
   curl http://localhost:8000/health
   docker compose exec db psql -U alfakurs -d alfa_events -c '\dt'
   docker compose logs worker --tail 20
   ```

   The UI preview path does **not** send impression or click events, because the
   catalogue preview creates no decision IDs. Event storage is exercised by the
   backend tests and by the real recommendation path, not by this preview. Do not
   claim live CTR from this demo.

---

## 4. What is real vs synthetic

| Area | Status |
|---|---|
| FastAPI app, sessions, CSRF, migrations | real, runs in the stack |
| Product DB and events DB | real PostgreSQL, created by compose |
| BM25 / TF-IDF / prior / LinUCB / slate code | real code, covered by tests |
| Dense vector channel (LSA, 64D) | real TF-IDF → SVD model over chunk text + descriptions/topics/tags, checksummed dataset |
| BM25 + dense fusion | per-query score scaling, 60/40 combination, same code in preview and serving |
| Event storage and reward worker | real code, runs against the events DB |
| Recommendation cards in the Docker demo | real hybrid retrieval + prior + LinUCB over a **synthetic** catalogue |
| `POST /api/v1/catalogue/rank` preview | real hybrid + prior scores, dense cosine, read-only LinUCB state, **no decision or event** |
| Daily question, roadmap, interest radar, profile analysis | deterministic demo rules, **not trained models** |
| Organizer catalogue, index, private E5 weights | **absent (private)** |
| CTR, conversion, sales, business uplift | **not measured** |
| Live product analytics | **not wired**; `/analytics` shows local learning actions, model evaluation is a closed disclosure |

The catalogue is explicitly synthetic: `scripts/build_demo_catalog.py` reads the
tracked 12-course CSV (`data/courses/courses.csv`) plus eight fictional materials
(six articles, one checklist document, one webinar), and runs the real preparation
pipeline over them inside the stack. Titles, descriptions, prices and links are
invented; the UI labels the catalogue as synthetic on the dashboard and the feed.
No personal data, no organizer archive, no real customer records are included.

The retrieval regression set is tracked too:
`data/synthetic/retrieval_cases_v2.json` contains 100 hand-written Russian
business tasks, including explicit `empty` and `out_of_vocabulary` cases. Run
the coverage diagnostic against the real demo catalogue with:

```bash
python scripts/evaluate_demo_queries.py --json reports/demo_query_eval.json
```

It reports how many tasks retrieve any material, lists dead-ends, and checks that
empty/out-of-vocabulary tasks stay empty. It has no relevance judgments, so it is
a coverage diagnostic, not a quality benchmark. `backend/tests/test_demo_query_coverage.py`
guards the same cases in CI, including that every hit carries both a BM25 and a
dense evidence channel and that the dense dataset is finite and row-aligned.

Current result on the shipped 20-item catalogue: **89/89** evaluable normal
queries match, **10/10** behaviour cases pass (empty, out-of-vocabulary,
unavailable format). One case (`dev034`, a calculator request) is reported
separately because the demo catalogue has no calculator format.

---

## 5. Optional: real private catalogue

The real ML path is implemented but needs two private inputs that are not in
this repository:

- `data/processed/catalog` — the verified public catalogue bundle;
- `artifacts/retrieval` — the BM25/TF-IDF index built from that bundle;
- `artifacts/embedding` — optional dense vector dataset (built by
  `scripts/build_demo_catalog.py --embedding-dir`; without it the API fits a
  deterministic LSA model in memory from the same public chunks).

When you have them, mount them and switch the stack to API mode:

```bash
# .env
ALFA_RECOMMENDATIONS_ENABLED=true
ALFA_SESSION_COOKIE_SECURE=false
VITE_RECOMMENDATIONS_SOURCE=api
VITE_API_BASE_URL=
ALFA_CATALOG_DIR=/private/catalog
ALFA_RETRIEVAL_INDEX_DIR=/private/retrieval
ALFA_EMBEDDING_DIR=/private/embedding
```

Then add read-only mounts for those two paths to the `api` service (and rebuild
the frontend, because Vite variables are build-time). See
`docs/integration-stage8.md` and `docs/catalog_stage2.md` for the bundle format
and verification commands. Without these paths the API intentionally fails
closed and the UI stays in demo mode.

---

## 6. Running tests and builds

Backend (from the repository root):

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```

Windows PowerShell uses the same line (`$env:PYTHONPATH='backend'` then
`python -m pytest backend/tests -q`).

Frontend (use `npm.cmd` instead of `npm` when PowerShell blocks `npm.ps1`):

```bash
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

The backend test suite contains database-marked tests that need
`ALFA_EVENTS_TEST_DATABASE_URL` and `ALFA_PRODUCT_TEST_DATABASE_URL`; they are
skipped when no isolated PostgreSQL test databases are configured.

### Backend without Docker (manual PostgreSQL)

Verified on PostgreSQL 16.9 with a database `alfakurs`, a role `alfa_events`
and databases `alfa_events` / `alfa_events_test` (the same names compose uses):

```bash
export DATABASE_URL=postgresql+psycopg://alfakurs@127.0.0.1:5432/alfakurs
export ALFA_EVENTS_DATABASE_URL=postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:5432/alfa_events
export ALFA_SESSION_SECRET=dev-only-insecure-session-secret-change-me-0001
export PYTHONPATH=backend

python -m alembic -c backend/product-alembic.ini upgrade head
python scripts/migrate_events.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, with the same variables:

```bash
python scripts/reward_worker.py --interval 30
curl http://127.0.0.1:8000/health          # {"status":"ok"}
psql "$ALFA_EVENTS_DATABASE_URL" -c '\dt'  # events tables
```

`ALFA_SESSION_SECRET` must be at least 32 bytes. For the full database test
suite add `ALFA_EVENTS_TEST_DATABASE_URL` (pointing at `alfa_events_test`) and
`ALFA_PRODUCT_TEST_DATABASE_URL` (pointing at `alfa_product_test`).

Current backend run without database: **234 passed, 66 skipped, 0 failed**
(including the frozen-query regression and dense-dataset tests). Database-marked
tests and the frontend suite were last reported in `docs/submission-report.md`;
rerun them in your environment before quoting those older numbers.

---

## 7. Known limitations

- **The demo catalogue is fictional, the ranking is not.** Recommendations are
  produced by the real hybrid retrieval (BM25 + LSA dense vectors) + prior +
  LinUCB path over a 20-item synthetic catalogue. LinUCB cannot learn a
  meaningful policy from a demo session; the private catalogue and real
  interaction history are required for that.
- **Product analytics is not live.** `/analytics` reads local demo actions and
  keeps the historical retrieval NDCG@10 behind a disclosure; CTR and conversion
  are not measured.
- **There is one local profile.** The separate server-side registration screen
  was removed so editing the questionnaire updates the same profile instead of
  creating a duplicate record. The `/api/v1/users/` endpoint remains in the API.
- **Search handles morphology and synonyms, not typos.** «клиентв» is not
  corrected to «клиент»; the analyzer stems known word forms and maps a fixed,
  inspectable business thesaurus.
- **Sometimes only one card is returned** for narrow queries; this is a
  retrieval limitation, not a UI bug.
- **External material opening and payments are not implemented.**
  `material_open` returns 503 and there is no payment adapter, so conversion
  and sales cannot be measured.
- **Events on tab close are not guaranteed.** Visibility and click events are
  best-effort; the browser may drop the last request.
- **The dense channel is LSA, not E5.** It is a real TF-IDF → SVD model with
  persisted vectors, but it is not a transformer encoder. Private E5 weights are
  not shipped; `e5_retriever.py` can replace the encoder without changing fusion
  or ranking.
- **Retrieval metrics are small-sample.** `docs/quality_stage56.md` reports
  NDCG@10 for 21 tasks labelled by one agentic labeller; private labels are not
  available. Treat them as a regression signal, not production relevance.
- **The reward worker learns from simulated events only in tests.** No real
  purchase traffic exists in the demo.

---

## 8. Repository map

```
backend/
  app/
    api/                 FastAPI routers (users, courses, interactions, recommendations)
    core/                settings, anonymous sessions
    database/            product and events engines
    data_preparation/    catalog, chunks, profiles, ranking/retrieval bundles
    ml/                  BM25, LSA dense vectors, hybrid fusion, features,
                         prior, LinUCB, slate, reward
    models/              SQLAlchemy models (product + events + learning)
    services/            orchestrator, ML provider, event service, learning
    main.py              app factory, lifespan, /health
  alembic/               product DB migrations
  migrations/            events DB migrations
  tests/                 backend test suite
frontend/
  src/pages/             Onboarding, Feed, Analytics, Registration, Profile
  src/services/          API client, demo matcher, visibility tracking
  Dockerfile             Node build → nginx
scripts/
  migrate_events.py      events migrations
  reward_worker.py       delayed reward projection loop
  sql/init_events.sql    creates the events databases on a fresh volume
  local/demo.mjs         Docker-free demo runner used by start-demo.cmd
start-demo.cmd           one-click Windows demo (no Docker, no database)
compose.yaml             one-command demo stack
docs/                    stage reports, methodology, integration audit
presentation/            business deck sources and PDF
```

Project history and the detailed stage narrative are in
`docs/README-history.md`; the staged roadmap is historical (see
`PROJECT_ROADMAP.md`).
