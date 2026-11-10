# backend/app/models/

SQLAlchemy ORM tables. One file per entity group.

## Files

| File | Tables | Notes |
|---|---|---|
| `user.py` | `users` | profile fields, no secrets |
| `course.py` | `courses` | catalogue + attributes |
| `recommendation.py` | `recommendations`, `impressions`, `bandit_state` | output + display log + model state |
| `interaction.py` | `interactions` | every event, one row each |

## Design notes

- UUID primary keys.
- `timestamptz` via `server_default=func.now()`.
- JSONB for lists/maps (`interests`, `skills`, `objectives`).
- Explicit indexes on the columns analytics filters by.
- FKs cascade on user/course deletion.

## Key relationships

```
users 1-* recommendations
users 1-* impressions
users 1-* interactions
courses 1-* recommendations
courses 1-* impressions
courses 1-* interactions
recommendations 1-* impressions
```

## Rules

- Models describe storage, not rules. No reward math, no ranking.
- Never store simulator preferences here.
- Schema changes go through Alembic, never `create_all` in production paths.

## Full DDL reference

[`docs/database_design.md`](../../../docs/database_design.md)

## What to learn

Declarative models, relationships, index selection, and why constraints belong in
the database as well as the application.
