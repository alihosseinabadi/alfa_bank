# Database Design

PostgreSQL schema for Alfa-Kurs. Implemented with SQLAlchemy models and managed with
Alembic migrations.

---

## 1. Entity-relationship diagram

```
┌─────────┐         ┌──────────────────┐         ┌─────────┐
│  users  │1       *│  recommendations │*       1│ courses │
└────┬────┘─────────└────────┬─────────┘─────────└────┬────┘
     │1                      │1                       │1
     │                       │                        │
     │*                      │*                       │*
┌────▼────────┐        ┌─────▼──────┐          ┌──────▼───────┐
│ interactions│        │ impressions│          │ bandit_state │
└─────────────┘        └────────────┘          └──────────────┘
```

- A recommendation can produce many impressions (re-shown over time).
- An impression can lead to at most one purchase event (enforced in service logic).
- `bandit_state` is global and versioned, not per user.

## 2. Tables

### users
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | server default `gen_random_uuid()` |
| industry | text | index |
| business_stage | text | e.g. idea, launch, growth |
| experience | text | e.g. none, some, experienced |
| interests | jsonb | category → weight map |
| goals | jsonb | list of goal tags |
| created_at | timestamptz | default now |

Never store simulator preferences here. Production profiles contain only what the
user provided.

### courses
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| title | text | not null |
| description | text | not null |
| category | text | index |
| skills | jsonb | list |
| objectives | jsonb | list |
| difficulty | text | beginner/intermediate/advanced |
| duration_minutes | int | check > 0 |
| price | numeric(10,2) | check >= 0 |
| has_free_material | boolean | default false |
| created_at | timestamptz | |

### recommendations
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | FK users | on delete cascade |
| course_id | FK courses | on delete cascade |
| algorithm | text | random / popular / linucb |
| score | float8 | model score |
| rank | int | position in returned list |
| model_version | text | ties back to bandit_state |
| created_at | timestamptz | |

### impressions
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | FK users | index |
| course_id | FK courses | index |
| recommendation_id | FK recommendations | index |
| created_at | timestamptz | |

### interactions
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | FK users | index |
| course_id | FK courses | index |
| event_type | text | impression/click/inspect/purchase/no_interaction |
| reward | float8 | computed by reward engine |
| created_at | timestamptz | index |

### bandit_state
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| model_version | text | unique |
| parameters | jsonb | A and b serialized, or artifact path |
| alpha | float8 | exploration strength |
| updated_at | timestamptz | |

## 3. Indexes

| Index | Purpose |
|---|---|
| users(industry) | cohort analytics |
| courses(category) | retrieval fallback |
| impressions(user_id, created_at) | CTR window |
| impressions(course_id, created_at) | popularity window |
| interactions(user_id, created_at) | per-user history |
| interactions(event_type, created_at) | funnel analytics |
| recommendations(user_id, created_at) | feed reconstruction |

## 4. Constraints

- `price >= 0`, `duration_minutes > 0`.
- `event_type` restricted to the known set (check or enum).
- `interactions.reward >= 0`.
- FK cascades on user and course deletion.
- `bandit_state.model_version` unique.

## 5. Correct denominators

CTR and conversion are only valid if impressions are recorded at display time:

```
CTR         = clicks / impressions
conversion  = purchases / impressions
```

If impressions are missing, both ratios inflate. The recommendation service must
write impression rows in the same transaction as the recommendation rows.

## 6. Popularity baseline query (no leakage)

Popularity for the evaluation window must use **only data before that window**:

```sql
SELECT course_id, COUNT(*) AS clicks
FROM interactions
WHERE event_type = 'click'
  AND created_at < :window_start
GROUP BY course_id
ORDER BY clicks DESC
LIMIT 50;
```

Never use the full table: that leaks the future into the baseline and makes the
comparison meaningless.

## 7. Migrations

- Alembic from day one.
- One migration per logical schema change.
- Never edit an applied migration; add a new one.
- Seed data is a separate script, never a migration.

## 8. Retention and privacy

- No names, emails or payment data in this schema; it is a behavioral store only.
- Simulator preferences live in `experiments/`, never in `users`.
- Production deployment would add anonymization and retention policies (out of scope).
