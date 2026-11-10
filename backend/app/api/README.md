# backend/app/api/

HTTP layer. Thin wrappers: validate input, call a service, return a schema.

## Files

| File | Endpoints | Imports |
|---|---|---|
| `users.py` | register, profile | `schemas/user`, `services/*` |
| `courses.py` | list, detail | `schemas/course`, `services/*` |
| `recommendations.py` | GET recommendations | `services/recommendation_service` |
| `interactions.py` | impression, click, inspect, purchase | `services/interaction_service` |
| `analytics.py` | overview, comparison, regret | `services/*`, `experiments/metrics` |

## Rules

- One function per endpoint, small.
- Declare `response_model` so `/docs` is accurate.
- Raise `HTTPException` with a correct status; never return an error inside 200.
- No SQL, no NumPy, no business rules here.
- Reuse a shared dependency for the DB session.
- Interaction endpoints accept `impression_id`; recommendations return one per item.

## Typical route shape

```python
@router.get("/recommendations/{user_id}", response_model=RecommendationResponse)
def get_recommendations(user_id: UUID, limit: int = 10, db: Session = Depends(get_db)):
    return recommendation_service.for_user(db, user_id, limit)
```

## Test

```bash
pytest backend/tests/test_api.py -q
```

## What to learn

FastAPI `Depends`, response models, status codes, and keeping handlers so small that
they are boring — which is the point.
