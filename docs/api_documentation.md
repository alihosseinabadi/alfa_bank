# API Documentation

FastAPI endpoints for Alfa-Kurs. Interactive docs are generated at `/docs` when the
server runs; this file is the human-readable contract.

Base URL: `http://127.0.0.1:8000`
All bodies are JSON. All errors use `{"detail": "..."}` with a correct status code.

---

## Users

### POST /api/users/register
Create a user.

```json
{ "industry": "marketing", "business_stage": "growth", "experience": "some" }
```

`201` → `{ "id": "uuid" }`
`422` → validation error

### POST /api/users/profile
Update profile fields.

```json
{
  "user_id": "uuid",
  "industry": "marketing",
  "business_stage": "growth",
  "experience": "some",
  "interests": { "marketing": 0.9, "sales": 0.7 },
  "budget_sensitivity": 0.6,
  "goals": ["increase revenue", "hire first salesperson"]
}
```

`200` → full profile
`404` → user not found
`422` → interest outside `[0,1]` or unknown category

Note: profile responses never contain simulator preferences — those do not exist in
the production schema.

## Courses

### GET /api/courses
Query: `category?`, `difficulty?`, `has_free?`, `limit=50`, `offset=0`

`200` → `{ "items": [...], "total": 120 }`

### GET /api/courses/{course_id}

`200` → course object
`404` → not found

Every course carries `source` (provenance). Current catalogue is `synthetic`.

## Recommendations

### GET /api/recommendations/{user_id}
Query: `limit=10`, `algorithm=linucb`

```json
{
  "user_id": "uuid",
  "slate_id": "uuid",
  "algorithm": "linucb",
  "model_version": "2026-11-07T10:00:00Z",
  "items": [
    {
      "impression_id": "uuid",
      "course_id": "uuid",
      "title": "First Customers for Your Business",
      "category": "marketing",
      "difficulty": "beginner",
      "duration_minutes": 90,
      "price": 4900,
      "has_free_material": true,
      "retrieval_score": 0.72,
      "bandit_score": 1.84,
      "position": 0,
      "reason": "Matches your interest in marketing and sales."
    }
  ]
}
```

Side effects: writes **one `recommendation_impressions` row per item**, all sharing
`slate_id`, in a single transaction. There is no separate impression table.

`200` → ranked slate
`404` → user not found
`503` → database unavailable

## Interactions

Every interaction references the impression it came from. That reference is the
attribution key and the duplicate guard.

### POST /api/interactions/impression
Rarely used explicitly; recommendations create impressions. Kept for clients that
render a slate themselves.

```json
{
  "user_id": "uuid",
  "course_id": "uuid",
  "slate_id": "uuid",
  "position": 0,
  "algorithm": "linucb",
  "model_version": "v1",
  "retrieval_score": 0.72,
  "bandit_score": 1.84
}
```

`201` → `{ "impression_id": "uuid" }`
`409` → `(slate_id, position)` or `(slate_id, course_id)` already used

### POST /api/interactions/click
```json
{ "impression_id": "uuid" }
```
`201` → `{ "id": "uuid", "reward": 1.0 }`
`404` → impression not found
`409` → this impression already has a click

### POST /api/interactions/inspect
```json
{ "impression_id": "uuid", "material_id": "optional" }
```
`201` → `{ "id": "uuid", "reward": 1.0 }`
`409` → this impression already has an inspect

### POST /api/interactions/purchase
```json
{ "impression_id": "uuid" }
```
`201` → `{ "id": "uuid", "reward": 10.0 }`
`409` → impression already converted, course already purchased by this user, or the
impression is older than `PURCHASE_ATTRIBUTION_DAYS`

Optional convenience form for clients that do not hold an impression id:

```json
{ "user_id": "uuid", "course_id": "uuid", "impression_id": "optional" }
```

Resolution: use given `impression_id`; else the most recent impression for the pair;
else `409`.

Errors: `404` impression/user/course missing, `422` invalid body.

### Reward contract

| Event | Reward | Notes |
|---|---|---|
| click | +1 | once per impression |
| inspect | +1 | once per impression |
| purchase | +10 | once per impression and once per (user, course) |

A purchase supplements earlier engagement; it does not expand into click rewards.
Maximum per impression: 12.

## Analytics

### GET /api/analytics/overview
```json
{
  "impressions": 1200,
  "clicks": 310,
  "inspections": 140,
  "purchases": 22,
  "ctr": 0.258,
  "inspection_rate": 0.117,
  "conversion": 0.0183,
  "avg_reward": 1.42
}
```

The three rates use the **same denominator**: impressions.

### GET /api/analytics/comparison
Query: `seeds=10`, `users=200`, `rounds=50`

```json
{
  "seeds": 10,
  "policies": {
    "random":  { "cumulative_reward": 12.4, "ctr": 0.11, "inspection_rate": 0.05, "conversion": 0.004, "ndcg_at_10": 0.31 },
    "popular": { "cumulative_reward": 18.1, "ctr": 0.19, "inspection_rate": 0.08, "conversion": 0.009, "ndcg_at_10": 0.44 },
    "linucb":  { "cumulative_reward": 27.6, "ctr": 0.27, "inspection_rate": 0.12, "conversion": 0.016, "ndcg_at_10": 0.58 }
  },
  "confidence_intervals": {
    "linucb": { "cumulative_reward": [24.9, 30.3] }
  },
  "note": "Simulated results across 10 seeds, not production metrics."
}
```

### GET /api/analytics/regret
Query: `policy=linucb`, `seeds=10`

```json
{ "rounds": [0, 1, 2, ...], "cumulative_regret": [0, 0.4, 0.9, ...], "ci": [[...], [...]] }
```

Regret exists only in the simulator; the oracle never reaches the API's policy path.

## Health

### GET /health
`200` → `{ "status": "ok", "db": "ok" }`

---

## Error conventions

| Code | Meaning |
|---|---|
| 400 | malformed request the schema cannot express |
| 404 | referenced resource missing |
| 409 | state conflict (duplicate event, conversion, stale impression) |
| 422 | Pydantic validation failure |
| 503 | dependency unavailable (DB, model artifact) |

Never return `200` with an error body. Never leak stack traces.

## Versioning

Every impression stores `model_version`; every bandit state is versioned. Changing
the feature layout bumps `feature_version` and resets the artifact. Breaking API
changes bump a path prefix in a future version; not needed for the hackathon.
