# backend/app/models/

SQLAlchemy ORM tables. One file per entity group.

## Files

| File | Tables | Notes |
|---|---|---|
| `user.py` | `users` | profile fields incl. `budget_sensitivity`, no secrets |
| `course.py` | `courses` | catalogue + attributes + `source` provenance |
| `recommendation.py` | `recommendation_impressions`, `bandit_state` | **canonical** display log + model state |
| `interaction.py` | `interactions` | every event, one row each, FK to impression |

## The impression table is the core

`recommendation_impressions` is the **single canonical record** of a course shown to
a user. There is no separate `recommendations` table and no separate `impressions`
table.

```
id, user_id, course_id, slate_id, position,
retrieval_score, bandit_score, algorithm, model_version, shown_at
```

- one row = one course at one position in one slate
- `slate_id` groups everything returned by one recommendations call
- unique `(slate_id, position)` and `(slate_id, course_id)`
- `interactions.impression_id` is a required FK for user actions

## Key relationships

```
users 1-* recommendation_impressions
courses 1-* recommendation_impressions
recommendation_impressions 1-* interactions
```

`bandit_state` is global and versioned (shared model), keyed by `model_version` and
guarded by `feature_version`.

## Constraints that protect the data

- `interactions.event_type in ('click','inspect','purchase')`
- unique `(impression_id, event_type)` — at most one click, one inspect, one purchase
  per impression
- unique purchase per `(user_id, course_id)`
- `price >= 0`, `duration_minutes > 0`
- FKs cascade on user/course deletion

## Rules

- Models describe storage, not rules. No reward math, no ranking.
- Never store simulator preferences here.
- Schema changes go through Alembic, never `create_all` in production paths.

## Full DDL reference

[`docs/database_design.md`](../../../docs/database_design.md)

## What to learn

Declarative models, relationships, index selection, and why a unique constraint is a
better duplicate guard than application code.
