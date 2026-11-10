# Database Design

PostgreSQL schema for Alfa-Kurs. Implemented with SQLAlchemy and managed with Alembic.

**Key rule:** `recommendation_impressions` is the **single canonical record** of a
course shown to a user. There is no separate impressions table.

---

## 1. Entity-relationship diagram

```
┌─────────┐                ┌───────────────────────────┐                ┌─────────┐
│  users  │1              *│ recommendation_impressions│*              1│ courses │
└────┬────┘────────────────└─────────────┬─────────────┘────────────────└────┬────┘
     │1                                   │1                                  │1
     │                                    │                                   │
     │*                                   │*                                  │*
┌────▼────────────────────────────────────▼──────────────────────────────────▼────┐
│                                  interactions                                    │
└──────────────────────────────────────────────────────────────────────────────────┘

                        ┌──────────────┐
                        │ bandit_state │  (global, versioned)
                        └──────────────┘
```

- One row in `recommendation_impressions` = one course shown at one position in one slate.
- Every click/inspect/purchase references exactly one impression row.
- `bandit_state` is global (shared model), versioned.

## 2. Tables

### users
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | `gen_random_uuid()` |
| industry | text | index |
| business_stage | text | idea / launch / growth |
| experience | text | none / some / experienced |
| interests | jsonb | category → weight in [0,1] |
| budget_sensitivity | float8 | 0..1, stated at onboarding |
| goals | jsonb | list of goal tags |
| created_at | timestamptz | default now |

No hidden simulator preferences here — ever.

### courses
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| title | text | not null |
| description | text | not null |
| title_ru | text | nullable |
| category | text | index |
| skills | jsonb | list |
| objectives | jsonb | list |
| difficulty | text | beginner / intermediate / advanced |
| duration_minutes | int | check > 0 |
| price | numeric(10,2) | check >= 0 |
| has_free_material | boolean | default false |
| source | text | provenance, e.g. `synthetic` |
| created_at | timestamptz | |

### recommendation_impressions  ← canonical
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | FK users | not null, on delete cascade |
| course_id | FK courses | not null, on delete cascade |
| slate_id | UUID | groups the courses shown together |
| position | int | 0-based rank in the slate |
| retrieval_score | float8 | cosine similarity from retrieval |
| bandit_score | float8 | LinUCB score (0 when no model) |
| algorithm | text | linucb / random / popular |
| model_version | text | ties to bandit_state |
| shown_at | timestamptz | default now, index |

Constraints:
- `position >= 0`
- unique `(slate_id, position)` — no two courses claim the same slot
- unique `(slate_id, course_id)` — a course appears once per slate

### interactions
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| impression_id | FK recommendation_impressions | not null for user actions |
| user_id | FK users | denormalized for simple queries |
| course_id | FK courses | denormalized for simple queries |
| event_type | text | click / inspect / purchase |
| reward | float8 | computed by reward engine |
| created_at | timestamptz | index |

Constraints:
- `event_type in ('click','inspect','purchase')`
- `reward >= 0`
- **unique `(impression_id, event_type)`** — at most one click, one inspect, one
  purchase per impression. This is the duplicate guard.
- **unique `(user_id, course_id, event_type)` for `purchase`** — a course is bought
  once per user.

`impression_id` is the attribution key: it ties the action to the exact slate,
position and model version that produced it.

### bandit_state
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| model_version | text | unique |
| feature_version | text | must match `FEATURE_VERSION` |
| parameters | jsonb | serialized `A`, `b`, stats, or artifact path |
| alpha | float8 | exploration strength |
| updated_at | timestamptz | |

If `feature_version` differs from the running code, the model is discarded and a
fresh one is initialized (dimension mismatch is fatal otherwise).

## 3. Why one table instead of two

The old design had `recommendations` plus `impressions` storing `user_id` and
`course_id` again. That duplicated the display record and made "which ranking
produced this click?" ambiguous. A single row per displayed course removes the
ambiguity and gives every interaction an exact parent.

## 4. Indexes

| Index | Purpose |
|---|---|
| `users(industry)` | cohort analytics |
| `courses(category)` | retrieval fallback |
| `recommendation_impressions(user_id, shown_at)` | per-user history, CTR window |
| `recommendation_impressions(course_id, shown_at)` | popularity window |
| `recommendation_impressions(slate_id)` | reconstruct a slate |
| `interactions(user_id, created_at)` | per-user funnel |
| `interactions(event_type, created_at)` | funnel analytics |
| `interactions(impression_id)` | attribution joins |

## 5. Correct denominators

```
CTR                      = clicks / impressions
free-material inspection rate = inspect events / impressions
purchase conversion      = purchases / impressions
```

All three require impressions to be written **when the slate is displayed**, not
reconstructed later. The recommendation service writes the whole slate in one
transaction.

## 6. Attribution

A purchase is attributed to the impression it references:

```
purchase.impression_id -> recommendation_impressions.id -> (slate, position, model_version)
```

The bandit updates using the feature vector that was actually scored for that
impression. This is why `recommendation_impressions` must store enough to rebuild
`x` (user and course are still available; `feature_version` guards the layout).

Attribution window: a purchase may reference an impression up to
`PURCHASE_ATTRIBUTION_DAYS` (default 7) old. Older matches are rejected with `409`.
This prevents a months-old impression from claiming a new purchase.

## 7. Popularity baseline query (no leakage)

```sql
SELECT course_id, COUNT(*) AS clicks
FROM interactions
WHERE event_type = 'click'
  AND created_at < :window_start      -- strictly past
GROUP BY course_id
ORDER BY clicks DESC
LIMIT 50;
```

Using `<= :window_end` or the full table leaks the future and invalidates the
comparison. Covered by `tests/test_leakage.py`.

## 8. Migrations

- Alembic from the first schema commit.
- One migration per logical change; never edit an applied migration.
- Seed data is a script (`scripts/seed_database.py`), never a migration.
- Destructive changes require a data-migration plan.

## 9. Retention and privacy

- No names, emails, payment data.
- No hidden preferences.
- Anonymous ids only.
- Production would add anonymization and retention windows (out of scope).
