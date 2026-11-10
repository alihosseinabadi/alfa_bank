# backend/app/database/

Database connectivity: engine, session factory, declarative base.

## Files

| File | Purpose |
|---|---|
| `connection.py` | Create the SQLAlchemy engine and `SessionLocal` |
| `base.py` | `Base = declarative_base()` shared by all models |

## connection.py

```python
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- `pool_pre_ping=True` avoids stale connections after DB restarts.
- The session is a FastAPI dependency; routes never build their own.

## base.py

Defines the declarative base that every model inherits. Keeping it separate avoids
import cycles between `models` and `connection`.

## Rules

- No business logic.
- One session per request.
- Transactions are owned by services, not by routes.

## Test

`GET /health` reports DB status; a failing DB returns `503`, never a silent success.

## What to learn

Engine vs session, connection pooling, and why the `yield`-based dependency pattern
guarantees cleanup.
