# frontend/src/

Application source. Small, typed, and organized by responsibility.

## Folders

| Folder | Contains | Consumed by |
|---|---|---|
| `components/` | reusable UI pieces | pages |
| `pages/` | route screens | `App.tsx` |
| `services/` | API client | pages, hooks |
| `hooks/` | data-fetching hooks | pages |
| `types/` | shared TS types | everything |

## Files

| File | Purpose |
|---|---|
| `main.tsx` | React root, router, providers |
| `App.tsx` | route table |
| `index.css` | Tailwind entry + base styles |

## Component plan

- `Layout.tsx` — nav shell.
- `CourseCard.tsx` — title, category, difficulty, duration, price, free badge,
  purchase button, reason pill.
- `ReasonPill.tsx` — explains why a course is shown.
- `Loading.tsx` / `ErrorState.tsx` — honest UI states.
- `charts/*` — thin Recharts wrappers for each metric.

## Data flow

```
page -> hook -> services/api.ts -> backend
```

No component fetches directly, so the base URL and error handling live in one place.

## Types must mirror the backend

When `schemas/*.py` changes, update `types/*.ts`. A mismatch is a bug, not a nuance.

## What to learn

Component boundaries, hooks for async data, and why a single typed client beats
scattered `fetch` calls.
