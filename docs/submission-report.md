# Submission verification report

Run on 2026-11-16 (Moscow time) in `C:\Users\ASUS\Downloads\alfa_bank-integration`.

**Environment used for these checks**

| Item | Value |
|---|---|
| OS | Windows 11, timezone UTC+03:00 |
| Python | 3.12.10 (system), pip 25.0.1 |
| Node | v26.7.0, npm 11.x (invoked as `npm.cmd` because of the PowerShell execution policy) |
| Docker | **no Docker on Windows**; Docker Engine 29.1.3 + Compose 2.40.3 installed inside the existing WSL2 Ubuntu 26.04 distro (`docker` is still not on the Windows PATH) |
| LibreOffice | 26.8.3 (installed during this run, used only to export the deck to PDF) |
| Private organizer data | absent (`data/raw`, `data/processed`, `artifacts/` do not exist) |

Everything below is what actually ran. Anything not listed as run is listed as
**unverified** — it is not claimed to work.

---

## 1. Commands and results

### Backend tests

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```

Result (real tail):

```
211 passed, 66 skipped, 233 warnings in 144.88s (0:02:24)
```

- 0 failures, 0 errors.
- 66 skips are the database-marked tests that require
  `ALFA_EVENTS_TEST_DATABASE_URL` / a PostgreSQL test database; they were not
  configured on this machine.

### Frontend install, tests and build

```bash
npm.cmd ci --prefix frontend          # exit 0, "added 253 packages"
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build   # tsc -b && vite build, OK
```

Frontend tests (real tail):

```
ℹ tests 21
ℹ pass 19
ℹ fail 2
```

The two failures are in `frontend/tests/profile-session.test.mjs` and come from
the test file, not from the application code:

```
TypeError: Cannot set property crypto of #<Object> which has only a getter
```

The test does `globalThis.crypto = webcrypto` in a `before` hook, but
`globalThis.crypto` is a read-only getter. This was re-checked with Node
v20.20.2 (the version used by `frontend/Dockerfile`) and it **fails the same
way**:

```
# tests 2
# pass 0
# fail 2
```

So the suite is 19/21 on both Node 20 and Node 26. Per the task rules the test
was **not modified** to make it pass; fixing it means changing the test to use
`Object.defineProperty` or a local stub.

Build output (real tail):

```
✓ 56 modules transformed.
dist/index.html                    0.42 kB
dist/assets/index-DUHIGxBs.js    201.95 kB │ gzip: 66.08 kB
✓ built in 3.06s
```

### Presentation build

```bash
node presentation/business_2026_11_15/build.cjs   # with pptxgenjs 4.0.1 on NODE_PATH
```

Result: `Alfa-Kurs-business.pptx` regenerated (364 KB, 12 slides). The
hard-coded absolute `require` path was replaced with `require('pptxgenjs')`, so
the deck now builds on any machine with the package installed.

PDF export:

```bash
soffice --headless --convert-to pdf:impress_pdf_Export \
  --outdir <tmp> presentation/business_2026_11_15/Alfa-Kurs-business.pptx
```

Result: a 12-page PDF, copied to the repository root as
`Alfa-Kurs-presentation.pdf` and over the deck folder's
`Alfa-Kurs-business.pdf`. Verified by extracting page 1 text (`pypdf`) and by
rendering page 1 to PNG (`pypdfium2`) and inspecting it: Cyrillic, the GitHub
link, `cp .env.example .env && docker compose up --build`,
`http://localhost:5173`, the three steps and the synthetic-demo note are all
present and not clipped.

### Demo UI flow (local Vite + headless Chrome, no Docker)

The production bundle cannot be served without Docker here, so the UI was
checked on the Vite dev server with `VITE_RECOMMENDATIONS_SOURCE=demo` and a
scripted headless Chrome (puppeteer-core, local Chrome). It performed the three
README steps by typing into `#custom-goal`.

```
vat:      path=/feed  demoBanner=true  cards=["НДС для малого бизнеса",
          "Как выбрать налоговый режим", "Регистрация ИП"]
clients:  path=/feed  demoBanner=true  cards=["Как найти первых клиентов",
          "Каналы привлечения клиентов"]
offTopic: path=/feed  emptyState=true  cards=0
console:  one 404 (default /favicon.ico, not defined by the app)
```

This verifies the client-side demo path and its labels. It does **not** verify
nginx, the API proxy, containers or the real ML path.

### Clean-tree smoke test (no Docker)

```bash
git archive --format=tar HEAD | tar -x -C <fresh dir>
PYTHONPATH=<fresh>/backend python -c "import app.main as m; print(m.app.title)"
```

Result:

```
files in fresh copy: 318
app import ok: Alfa-Kurs API
routes: 9
```

This also confirmed that `scripts/migrate_events.py`,
`scripts/reward_worker.py` and `compose.yaml` are present in the committed
tree. It caught a real submission bug: the venv ignore pattern `Scripts/` was
also ignoring the lowercase `scripts/` directory on Windows, so the whole
directory was untracked. The pattern was removed in commit `6d0899c`.

### Compose file and Dockerfiles
- `compose.yaml` parses as YAML (PyYAML), validates against the official
  compose-spec JSON schema (fetched from the compose-spec repository), and
  declares services `db, migrate, api, worker, frontend` and volume
  `alfakurs_pgdata`.
- Images were built and the stack was started (see below).
- `backend/requirements.lock.txt` (66 pinned lines) is installed by
  `backend/Dockerfile`; the lock was produced by `pip freeze` in a clean
  Python 3.12 virtual environment with `backend/requirements.txt` +
  `backend/requirements-catalog.txt`. It was then installed into a second,
  empty virtual environment (`pip install -r backend/requirements.lock.txt`,
  exit 0) and the app imported there: `fastapi 0.163.1, numpy 2.5.5,
  scikit-learn 1.9.1`, `app.main` imports.

### Docker stack executed

Docker Desktop is not installed on this machine and `docker` is not on the
Windows PATH, but the WSL2 Ubuntu 26.04 distro was available. Docker Engine
29.1.3 and Compose 2.40.3 were installed inside it, and the judge command was
run unchanged from the repository directory (`/mnt/c/...`):

```bash
cp .env.example .env
docker compose up --build
```

Real result (first build, no cache):

```text
#13 naming to docker.io/library/alfakurs-api:local  ... DONE
frontend-1  | nginx/1.27 … start worker processes
```

```text
docker compose ps -a
api       running  0  healthy
db        running  0  healthy
frontend  running  0
migrate   exited   0
worker    running  0

docker compose exec db psql -U alfakurs -d alfa_events -c '\dt'
→ 12 tables (event_actors … unattributed_clicks), owner alfa_events
docker compose exec db psql -U alfakurs -d alfakurs -c '\dt'
→ 6 tables (users, courses, interactions, recommendation_impressions,
            bandit_state, alembic_version)
docker compose logs worker --tail 20
→ "Standard delayed reward policy"

curl http://localhost:8000/health   → {"status":"ok"}   HTTP 200
curl http://localhost:5173/health   → {"status":"ok"}   HTTP 200  (nginx → api)
curl http://localhost:5173/         → HTTP 200
GET  /feed, /analytics              → HTTP 200  (SPA fallback)
POST http://localhost:5173/api/v1/users/ → HTTP 201 (nginx /api proxy)
```

The three-step demo flow was then driven through the **nginx-served** build with
headless Chrome: «…НДС?» → 3 cards, «…первых клиентов?» → 2 cards, «Как починить
карбюратор» → empty state, demo banner present, **no console errors**.

### Local PostgreSQL stack (a second, Docker-free run of the same commands)

Before Docker was available, the commands from `compose.yaml` were also executed
natively against **PostgreSQL 16.9** (EDB Windows binaries, `initdb`, listening
on `127.0.0.1:55432`, role `alfa_events` / password `local_events_only`,
databases `alfakurs`, `alfa_events`, `alfa_events_test`, `alfa_product_test`).

```bash
python -m alembic -c backend/product-alembic.ini upgrade head
python scripts/migrate_events.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python scripts/reward_worker.py --once
curl http://127.0.0.1:8000/health
```

Real results:

```
product DB  \dt → users, courses, interactions, recommendation_impressions,
                  bandit_state, alembic_version                   (6 tables)
events  DB  \dt → alembic_version, event_actors, event_receipts,
                  interaction_events, recommendation_decisions,
                  recommendation_impressions, recommendation_items,
                  reward_observations, reward_revisions, serving_requests,
                  slate_random_seeds, unattributed_clicks        (12 tables)
migrate_events.py → "Product events migrations applied"
GET  /health      → {"status":"ok"}  HTTP 200   (/openapi.json HTTP 200)
POST /api/v1/users/ → HTTP 201, row visible in `users`
reward_worker.py --once → exit 0 ("Standard delayed reward policy")
```

This exercises the same migration files, settings and endpoints as the compose
services. It does **not** exercise the Docker images, the entrypoint order or
the nginx proxy.

The same PostgreSQL also ran the whole backend suite with the database-marked
tests enabled:

```text
ALFA_EVENTS_TEST_DATABASE_URL=...alfa_events_test
ALFA_PRODUCT_TEST_DATABASE_URL=...alfa_product_test
python -m pytest backend/tests -q
→ 276 passed, 1 skipped, 233 warnings in 175.53s
```

---

## 2. What is verified vs unverified

| Item | Status |
|---|---|
| Backend test suite (no DB) | **verified** — 211 passed, 66 skipped, 0 failed |
| Backend DB-marked tests | **verified** — with `alfa_events_test` + `alfa_product_test`: **276 passed, 1 skipped, 0 failed** (the skip is the real-tokenizer test, which needs the private catalogue pipeline) |
| Backend dependency lock installs from scratch | **verified** — clean venv, exit 0, app imports |
| Frontend `npm ci` / production build | **verified** |
| Frontend tests | **19/21 pass**; 2 fail in a test-side `globalThis.crypto` assignment (same on Node 20 and Node 26) |
| Deck regenerated to pptx | **verified** |
| Deck exported to PDF | **verified** — 12 pages, slide 1 inspected |
| `docker compose up --build` | **verified** — images built, `migrate` exit 0, `db`/`api` healthy |
| `compose.yaml` against the compose-spec JSON schema | **verified** |
| Committed tree completeness (fresh `git archive` + app import) | **verified** — 318 files, app imports |
| Demo UI flow: НДС → 3 cards, clients → 2 cards, off-topic → empty state, demo banner shown | **verified** on the local Vite dev server with headless Chrome |
| `start-demo.cmd` (Docker-free launcher) | **verified** — installs deps, serves on 127.0.0.1:5173, HTTP 200 |
| Same UI flow through nginx in the Docker image | **verified** — same cards, no console errors |
| `/health` against real PostgreSQL 16.9 | **verified** — HTTP 200 `{"status":"ok"}` |
| Product + events migrations on real PostgreSQL 16.9 | **verified** — 6 product tables, 12 events tables |
| Registration endpoint against real PostgreSQL | **verified** — HTTP 201, row in `users` |
| Reward worker against the real events DB | **verified** — `--once`, exit 0 |
| The same steps inside the Docker images / fresh volume | **verified** — containerised `\dt`, worker log, nginx `/api` → 201 |
| Real BM25/prior/LinUCB path on the organizer catalogue | **unverified** — private catalogue and index absent |
| CTR, conversion, sales, business effect | **not measured** — no live traffic, no payments |

The demo UI path is synthetic and is labelled as such in the UI, README and
deck. It does not emit impression or click events, because demo cards carry no
decision IDs; events and the reward worker are exercised by backend tests and by
the real API path only.

---

## 3. Secrets and private-data audit

- Working tree: only `.env.example` matches any `.env*` pattern. No `.env`,
  `backend/.env` or secret file exists on disk.
- `git ls-files` (255 files) contains no `.env`, no `*.backup`, no `data/raw`,
  `data/processed`, `data/interim`, `artifacts/`, `reports/`, no archive, dump,
  key or token file. The only match for the audit pattern was `.env.example`.
- `.gitignore` ignores `.env`, `.env.*` (except `.env.example`), `artifacts/`,
  `data/raw/`, `data/interim/`, `data/processed/`, `reports/`, `*.backup`,
  `*.dump`, model weights, `node_modules/`, `dist/`.
  `git check-ignore` confirmed each of those paths is ignored.
- History: this snapshot arrived without `.git`. A local repository was
  initialised for the submission and contains a single import commit
  (`a43d0f1`), so **no historical commit can leak private files here**. The
  original multi-branch repository history was not available to audit locally.
- `docker build` context is filtered by `.dockerignore` files that exclude
  `.env`, `data/raw`, `data/interim`, `data/processed`, `artifacts`, `reports`,
  `*.backup`, `*.zip`, `presentation` and model archives.

---

## 4. Known gaps left in this submission

1. **Docker was run in WSL2, not through Docker Desktop.** The stack itself
   (images, migrations, health, proxy, worker) is verified, but the exact
   one-command path on a plain Windows machine with Docker Desktop is still not
   exercised here: on this box `docker` exists only inside the Ubuntu distro.
   A Docker Desktop install needs admin rights and a reboot.
2. **Events database credentials are duplicated** in
   `scripts/sql/init_events.sql` (role `alfa_events`, password
   `local_events_only`). Changing `ALFA_EVENTS_*` in `.env` requires editing the
   SQL file too.
3. **No real catalogue** means the ML path cannot be demonstrated end to end;
   the UI runs in explicitly labelled demo mode.
4. **Frontend tests** are 19/21: two tests assign the read-only
   `globalThis.crypto`, so they fail on Node 20 and Node 26 alike. Fixing that
   requires editing the test file, which was out of scope here.

---

## 5. Slide 1 text in the generated PDF (for reference)

Title: `Рекомендации для Альфа-Курса`

Subtitle: `Alfa-Kurs · трек «Персонализация образования для предпринимателей» · автор: alihosseinabadi`

Left block:

```
ОТ БИЗНЕС-ЗАДАЧИ
к подходящему
следующему шагу

BM25 → признаки → prior → LinUCB → подборка материалов. В демо для жюри
каталог вымышленный, карточки помечены как демонстрационные.
```

Right panel — «Как проверить за 3 шага»:

```
1. cp .env.example .env && docker compose up --build
2. Открыть http://localhost:5173
3. Ввести «Как предпринимателю разобраться с НДС?» — появятся три демокарточки.

Демо: материалы вымышлены и подписаны; конверсия, продажи и бизнес-эффект
не измерялись.
```

Footer:

```
github.com/alihosseinabadi/alfa_bank
Docker-стек в этом окружении не запускался (Docker недоступен);
каталог демо синтетический, код API, событий и воркера реальный
```

---

## 6. Manual steps required before sending the link

1. Install Docker Desktop (Compose v2) and run, in a fresh copy:
   `cp .env.example .env && docker compose up --build`.
2. Open http://localhost:5173 and complete the three test steps from the README
   (НДС task → clients task → off-topic empty state).
3. Check `curl http://localhost:8000/health` and
   `docker compose exec db psql -U alfakurs -d alfa_events -c '\dt'`.
4. Open `Alfa-Kurs-presentation.pdf` and check that slide 1 renders as expected
   in your PDF viewer (the deck was exported with LibreOffice 26.8).
5. Optional: fix the two failing frontend tests by replacing the test-side
   `globalThis.crypto = webcrypto` assignment (they fail on Node 20 and 26;
   the application code is not involved).
