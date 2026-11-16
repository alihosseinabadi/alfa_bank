# Alfa-Kurs — adaptive learning recommendations

**Кратко по-русски.** Alfa-Kurs подбирает учебные материалы предпринимателям по
их задаче: BM25-поиск → признаки → prior-ранжирование → LinUCB → слэйт → события
показов и кликов. В Docker-демо для жюри каталог **синтетический**: он
генерируется скриптом внутри стека, а рекомендации выдаёт настоящий конвейер
BM25 → prior → LinUCB, и UI помечает такой каталог как демонстрационный. Реальный
каталог организатора приватен и в репозиторий не входит. Конверсия, продажи и
эффект обучения на живых данных **не измерялись**.

A hackathon project for the Alfa-Bank Web/AI hackathon, track
"Personalization of education for entrepreneurs". The product is a task-first
recommender for the Alfa-Kurs catalogue: a user describes a business task, gets
ranked learning materials with explanations, and the system records impressions,
visibility and clicks that feed a reward worker.

**Presentation:** [`Alfa-Kurs-presentation.pdf`](Alfa-Kurs-presentation.pdf) — 12
slides in Russian, slide 1 contains the run command and three test steps.
**Verification record:** [`docs/submission-report.md`](docs/submission-report.md).

---

## 1. What it is

Profile / task → BM25 retrieval (top-50) → feature builder → prior ranking →
LinUCB → slate shaping → explanations → UI. The same path records canonical
impressions and interactions; a background worker projects delayed rewards and
updates the shared LinUCB model.

```
 task / profile
      │
      ▼
 BM25 retrieval ──► candidate materials (top-50)
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
TF-IDF retrieval, the 22-feature builder, deterministic prior ranking, shared
LinUCB, slate policy, internal event service, reward ledger and replay,
anonymous signed sessions with CSRF, two Alembic migration chains, and this
Docker demo stack. What is not: real organizer data, live payments, external
material opening, live analytics, and a measured business effect.

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
- The stack generates a **synthetic demo catalogue** inside a shared volume
  (`scripts/build_demo_catalog.py`) and runs the **real ML path** on it: BM25 →
  prior ranking → LinUCB → slate. The UI calls the API, so cards come from that
  pipeline, and both the dashboard and the feed carry a visible
  «синтетический каталог» notice. No catalogue or index is baked into the images.
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

Use the UI at **http://127.0.0.1:5173** (or the port you chose). Steps 1–4 work
in both quick-start options; registration and event checks need the API
(Option A, or the manual backend in section 6).

1. **Sign up.** The app opens on the sign-in screen. Register with any name and
   e-mail (the password is never sent) or press «Войти в демо без регистрации».
2. **Six questions.** Answer with the choice cards: main task, sphere, stage,
   experience, what blocks you most, then describe the situation in your own
   words. The right panel shows the profile filling up; «Назад» returns to any
   step, and the last button says «Открыть дашборд».
3. **Dashboard.** The greeting shows your name, the profile card shows a
   readiness bar, your answers as chips and free text, the focus card repeats
   your task, «Что открыть первым» shows the two matching demo cards, and the
   checklist toggles the three suggested steps.
4. **Recommendations.** «Смотреть все рекомендации» opens the full feed: «Как
   найти первых клиентов?» gives two client cards, «Как разобраться с НДС?»
   gives three tax cards, «Как починить карбюратор» gives an explicit empty
   state. Each card carries a short "why" line and a type label; these are demo
   explanations, not model explanations.
5. **State.** Refresh the page: the account, answers and readiness bar are
   restored from browser storage. «Выйти» clears them.
6. **Registration in the API.** Open «Профиль» → registration. This form writes
   a user into the product database and needs a reachable API; it is the only
   screen that stores anything server-side. It accepts the three preset goals
   and is not linked to the anonymous session — a known limitation.
7. **Backend and events.** The API, databases and worker run even in demo mode.
   To inspect them:

   ```bash
   curl http://localhost:8000/health
   docker compose exec db psql -U alfakurs -d alfa_events -c '\dt'
   docker compose logs worker --tail 20
   ```

   The UI demo path does **not** send impression or click events, because demo
   cards have no decision IDs. Event storage is exercised by the backend tests
   and by the real API path, not by the demo UI. Do not claim live CTR from this
   demo.

The «Аналитика» screen is a **static historical evaluation panel**, not live
analytics. It shows the numbers that exist in `docs/quality_stage56.md` and
explicitly says that CTR and conversion were not measured.

---

## 4. What is real vs synthetic

| Area | Status |
|---|---|
| FastAPI app, sessions, CSRF, migrations | real, runs in the stack |
| Product DB and events DB | real PostgreSQL, created by compose |
| BM25 / TF-IDF / prior / LinUCB / slate code | real code, covered by tests |
| Event storage and reward worker | real code, runs against the events DB |
| Recommendation cards in the Docker demo | real BM25 + prior + LinUCB over a **synthetic** catalogue |
| Organizer catalogue, index, E5 artifacts | **absent (private)** |
| CTR, conversion, sales, business uplift | **not measured** |
| Live analytics screen | **not wired** (static historical panel) |

The catalogue is explicitly synthetic: `scripts/build_demo_catalog.py` writes six
fictional materials (articles, courses, a document and a webinar) and runs the
real preparation pipeline over them inside the stack. Titles, descriptions and
links are invented; the UI labels the catalogue as synthetic on the dashboard and
the feed. No personal data, no organizer archive, no real customer records are
included.

---

## 5. Optional: real private catalogue

The real ML path is implemented but needs two private inputs that are not in
this repository:

- `data/processed/catalog` — the verified public catalogue bundle;
- `artifacts/retrieval` — the BM25/TF-IDF index built from that bundle.

When you have them, mount them and switch the stack to API mode:

```bash
# .env
ALFA_RECOMMENDATIONS_ENABLED=true
ALFA_SESSION_COOKIE_SECURE=false
VITE_RECOMMENDATIONS_SOURCE=api
VITE_API_BASE_URL=
ALFA_CATALOG_DIR=/private/catalog
ALFA_RETRIEVAL_INDEX_DIR=/private/retrieval
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

Submission-run results: backend **211 passed, 66 skipped, 0 failed** without a
database and **276 passed, 1 skipped, 0 failed** against PostgreSQL 16.9 with
both test databases (the one skip needs the private catalogue pipeline);
frontend **19 passed, 2 failed** (both failures are a test-side
`globalThis.crypto` assignment, see `docs/submission-report.md`).

---

## 7. Known limitations

- **Demo recommendations are fictional.** They are keyword-matched examples,
  not the BM25/LinUCB model. The real model needs the private catalogue.
- **Analytics is not live.** The screen is a static historical retrieval
  evaluation; CTR and conversion are not measured.
- **Registration is not linked to the anonymous session** and accepts only the
  three preset goals in the form. There is no re-login.
- **Search is typo-sensitive.** For example, «клиентв» returns nothing in the
  real BM25 path; the demo matcher is a simple keyword set.
- **Sometimes only one card is returned** by the real provider for narrow
  queries; this is a retrieval limitation, not a UI bug.
- **External material opening and payments are not implemented.**
  `material_open` returns 503 and there is no payment adapter, so conversion
  and sales cannot be measured.
- **Events on tab close are not guaranteed.** Visibility and click events are
  best-effort; the browser may drop the last request.
- **E5 and the hybrid E5 path are unverified.** No model weights or vectors are
  shipped.
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
    ml/                  BM25, TF-IDF, features, prior, LinUCB, slate, reward
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
