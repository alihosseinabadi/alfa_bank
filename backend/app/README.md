# backend/app/

The application package. Everything the API imports lives here.

## Files and packages

| Path | Responsibility | Called by |
|---|---|---|
| `main.py` | Create the FastAPI app, mount routers, expose `/health` | uvicorn |
| `api/` | HTTP endpoints | FastAPI router |
| `core/` | Settings and constants | everything |
| `database/` | Engine + session + Base | models, services |
| `models/` | ORM tables | services, migrations |
| `schemas/` | Request/response models | api |
| `services/` | Business workflows | api |
| `ml/` | Algorithms | services, experiments |

## Dependency direction

```
main -> api -> services -> {ml, models}
models -> database
api -> schemas
core -> (imported everywhere, imports nothing app-specific)
```

No cycles. `ml/` depends only on NumPy/Pandas/scikit-learn and `core/`.

## main.py responsibilities

1. Load settings.
2. Create the FastAPI instance (title, version, docs URL).
3. Add CORS for the dev frontend.
4. Mount routers under `/api`.
5. Register exception handlers.
6. `/health` returns app + DB status.

It must **not** contain route logic.

## What to learn

Application factories, router composition, and dependency injection as the seam
between HTTP and domain logic.
