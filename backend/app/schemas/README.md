# backend/app/schemas/

Pydantic models that define the API contract. Shared by routes and tests.

## Files

| File | Models |
|---|---|
| `user.py` | `UserCreate`, `UserProfileUpdate`, `UserRead` |
| `course.py` | `CourseRead`, `CourseList` |
| `interaction.py` | `ImpressionCreate`, `ClickCreate`, `InspectCreate`, `PurchaseCreate`, `InteractionRead` |
| `recommendation.py` (planned) | `RecommendationItem`, `RecommendationResponse` (includes `slate_id`, `impression_id`, `retrieval_score`, `bandit_score`, `position`) |
| `analytics.py` (planned) | `Overview`, `Comparison`, `Regret` |

## Rules

- Request models validate types and ranges (e.g. `price >= 0`, `0 <= interest <= 1`).
- Interaction requests carry `impression_id`; it is the attribution key.
- `PurchaseCreate` also accepts `user_id` + `course_id` for the "most recent
  impression" resolution path.
- Response models are explicit — never expose ORM objects directly.
- `Config.orm_mode = True` (Pydantic v2: `from_attributes = True`) for ORM reads.
- No business logic in schemas; no simulator preferences anywhere.

## Why this matters

Schemas are the boundary. If the API and the frontend agree on these objects, the
TypeScript `types/` mirror them exactly and integration bugs drop sharply.

## Mirror in frontend

`frontend/src/types/` must match these shapes. When a schema changes, update both.

## What to learn

Pydantic validation, `from_attributes`, and designing response contracts that do not
leak internal columns.
