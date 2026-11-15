# backend/

The FastAPI application, ML modules and tests. One deployable Python service.

## Layout

```
backend/
├── app/
│   ├── main.py            # app factory, router mounting, /health
│   ├── api/               # HTTP layer (thin)
│   ├── core/              # settings, constants, logging
│   ├── database/          # engine, session, Base
│   ├── models/            # SQLAlchemy tables
│   ├── schemas/           # Pydantic contracts
│   ├── services/          # business workflows / transactions
│   └── ml/                # pure algorithms (no FastAPI, no DB)
├── requirements.txt       # pinned-ish dependencies
├── alembic/               # migrations (created in phase 1)
└── tests/                 # unit + API tests
```

## Layering rule

```
api  ->  services  ->  ml
                  \->  models  ->  database
```

- `api/` validates and delegates. No ML math, no SQL.
- `services/` owns transactions and combines components.
- `ml/` is pure. It must not import FastAPI or open sessions.

## Run

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://127.0.0.1:8000/docs
```

## Test

```bash
pytest backend/tests -q
```

## Files planned here

| File | Purpose |
|---|---|
| `requirements.txt` | FastAPI, SQLAlchemy, Alembic, psycopg, NumPy, Pandas, scikit-learn, pytest |
| `alembic.ini`, `alembic/` | migration config and versions |
| `tests/` | ML and API tests |

## What to learn

FastAPI dependency injection, Pydantic validation, SQLAlchemy sessions, and why
keeping ML free of framework imports makes it trivially testable.
