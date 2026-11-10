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
  "goals": ["increase revenue", "hire first salesperson"]
}
```

`200` → full profile
`404` → user not found

## Courses

### GET /api/courses
Query: `category?`, `difficulty?`, `has_free?`, `limit=50`, `offset=0`

`200` → `{ "items": [...], "total": 120 }`

### GET /api/courses/{course_id}

`200` → course object
`404` → not found

## Recommendations

### GET /api/recommendations/{user_id}
Query: `limit=10`, `algorithm=linucb`

```json
{
  "user_id": "uuid",
  "algorithm": "linucb",
  "items": [
    {
      "course_id": "uuid",
      "title": "Marketing for First Customers",
      "category": "marketing",
      "difficulty": "beginner",
      "duration_minutes": 90,
      "price": 4900,
      "has_free_material": true,
      "score": 1.84,
      "rank": 1,
      "reason": "Matches your interest in marketing and sales."
    }
  ]
}
```

Side effects: persists recommendation + impression rows.
`200` → ranked list
`404` → user not found
`503` → database unavailable

## Interactions

### POST /api/interactions/impression
Explicit impression (normally created by recommendations).

```json
{ "user_id": "uuid", "course_id": "uuid", "recommendation_id": "uuid" }
```

`201` → `{ "id": "uuid" }`

### POST /api/interactions/click
```json
{ "user_id": "uuid", "course_id": "uuid" }
```
`201` → `{ "id": "uuid", "reward": 1.0 }`

### POST /api/interactions/inspect
```json
{ "user_id": "uuid", "course_id": "uuid", "material_id": "optional" }
```
`201` → `{ "id": "uuid", "reward": 1.0 }`

### POST /api/interactions/purchase
```json
{ "user_id": "uuid", "course_id": "uuid" }
```
`201` → `{ "id": "uuid", "reward": 10.0 }`
`409` → course already purchased by this user

Errors: `404` user/course/impression missing, `422` invalid body.

## Analytics

### GET /api/analytics/overview
```json
{
  "impressions": 1200,
  "clicks": 310,
  "inspections": 140,
  "purchases": 22,
  "ctr": 0.258,
  "conversion": 0.0183,
  "avg_reward": 1.42
}
```

### GET /api/analytics/comparison
Query: `seeds=5`, `users=200`, `rounds=50`

```json
{
  "policies": {
    "random":   { "cumulative_reward": 12.4, "ctr": 0.11, "conversion": 0.004 },
    "popular":  { "cumulative_reward": 18.1, "ctr": 0.19, "conversion": 0.009 },
    "linucb":   { "cumulative_reward": 27.6, "ctr": 0.27, "conversion": 0.016 }
  },
  "note": "Simulated results, not production metrics."
}
```

### GET /api/analytics/regret
Query: `policy=linucb`, `seeds=5`

```json
{ "rounds": [0, 1, 2, ...], "cumulative_regret": [0, 0.4, 0.9, ...] }
```

## Health

### GET /health
`200` → `{ "status": "ok", "db": "ok" }`

---

## Error conventions

| Code | Meaning |
|---|---|
| 400 | malformed request the schema cannot express |
| 404 | referenced resource missing |
| 409 | state conflict (duplicate purchase) |
| 422 | Pydantic validation failure |
| 503 | dependency unavailable (DB, model artifact) |

Never return `200` with an error body. Never leak stack traces.

## Versioning

Recommendations carry `model_version`. Analytics may filter by it. Breaking API
changes bump a path prefix in a future version; not needed for the hackathon.
