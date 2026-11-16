# Alfa-Kurs — adaptive learning recommendations

**Кратко по-русски.** Alfa-Kurs подбирает учебные материалы предпринимателям по
их задаче: BM25-поиск → признаки → prior-ранжирование → LinUCB → слэйт → события
показов и кликов. В Docker-демо для жюри каталог **вымышленный**, а рекомендации
помечены как демонстрационные. Реальный каталог организатора приватен и в
репозиторий не входит. Конверсия, продажи и эффект обучения на живых данных
**не измерялись**.

A hackathon project for the Alfa-Bank Web/AI hackathon, track
"Personalization of education for entrepreneurs". The product is a task-first
recommender for the Alfa-Kurs catalogue: a user describes a business task, gets
ranked learning materials with explanations, and the system records impressions,
visibility and clicks that feed a reward worker.

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
TF-IDF retrieval, the 45-feature builder, deterministic prior ranking, shared
LinUCB, slate policy, internal event service, reward ledger and replay,
anonymous signed sessions with CSRF, two Alembic migration chains, and this
Docker demo stack. What is not: real organizer data, live payments, external
material opening, live analytics, and a measured business effect.

---

## 2. Quick start for judges

Requires Docker Desktop with Compose v2. Nothing else, no private data.

> **Status of this snapshot.** The stack below was authored and reviewed but has
> not been executed on the author's machine (Docker was unavailable there). The
> backend tests, the frontend install and the frontend build were run; exact
> results and the list of unverified items are in
> [`docs/submission-report.md`](docs/submission-report.md).

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
- The UI is built in **explicit demo mode** (`VITE_RECOMMENDATIONS_SOURCE=demo`):
  cards are fictional and the banner says so. The API, both databases,
  migrations, sessions and the reward worker are real and start as part of the
  same stack.

If port 5173 or 8000 is busy, set `FRONTEND_PORT` / `API_PORT` in `.env`.

---

## 3. How to test the main features

Use the UI at http://localhost:5173.

1. **Onboarding.** The app opens on «Анкета». Keep the default task or type one.
2. **Example task 1 (taxes).** Enter
   «Как предпринимателю разобраться с НДС?» and press «Подобрать материалы».
   You should see three clearly labelled demo cards about НДС, tax regimes and
   ИП registration.
3. **Example task 2 (clients).** Go back to «Анкета», enter
   «Как найти первых клиентов?» and submit. The demo set changes to the
   client-acquisition examples. This shows that the task text drives the result.
4. **Explanations.** Each card carries a short "why" line and a type label.
   These are demo explanations, not model explanations.
5. **Off-topic query.** Enter «Как починить карбюратор» — the demo matcher has no
   category for it, so the UI shows an explicit empty state instead of inventing
   cards.
6. **State.** Refresh the page: the task and profile are restored from browser
   storage where the browser allows it. «Изменить» on the feed returns to the
   questionnaire.
7. **Registration.** Open «Профиль» → registration. Registration requires one of
   the three preset goals in the form and a reachable API; it is not linked to
   the anonymous session. This is a known limitation, not a demo feature.
8. **Backend and events.** The API, databases and worker run even in demo mode.
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
| Recommendation cards in the Docker demo | **fictional demo data** |
| Organizer catalogue, index, E5 artifacts | **absent (private)** |
| CTR, conversion, sales, business uplift | **not measured** |
| Live analytics screen | **not wired** (static historical panel) |

The demo catalogue is explicitly fictional: titles, descriptions and links are
invented for the UI. No personal data, no organizer archive, no real customer
records are included.

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

Frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build
```

The backend test suite contains database-marked tests that need
`ALFA_EVENTS_TEST_DATABASE_URL`; they are skipped when no PostgreSQL test
database is configured. The exact pass/skip counts from the submission run are
recorded in the final verification report (`docs/submission-report.md`).

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
compose.yaml             one-command demo stack
docs/                    stage reports, methodology, integration audit
presentation/            business deck sources and PDF
```

Project history and the detailed stage narrative are in
`docs/README-history.md`; the staged roadmap is historical (see
`PROJECT_ROADMAP.md`).
