# frontend/

React + TypeScript + Vite + Tailwind + Recharts. Three screens, wired to the real API.

## Screens

| Route | Screen | Purpose |
|---|---|---|
| `/onboarding` | Onboarding | collect industry, stage, experience, interests, challenges, goals |
| `/feed` | Personalized feed | ranked courses with reason + actions |
| `/analytics` | Analytics | LinUCB vs Random vs Popular, regret, CTR, conversion |

## Planned structure

```
frontend/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── index.css
    ├── components/     # CourseCard, ReasonPill, Chart wrappers, Layout
    ├── pages/          # Onboarding, Feed, Analytics
    ├── services/       # api.ts (typed fetch client)
    ├── hooks/          # useProfile, useRecommendations, useAnalytics
    ├── types/          # mirrors backend Pydantic schemas
    └── README.md
```

## Run

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check + bundle
```

Environment: `VITE_API_BASE_URL=http://127.0.0.1:8000`

## Rules

- No mock data in the committed app. If the API is down, show an error state.
- All API calls go through `services/api.ts`; components never call `fetch` directly.
- Types mirror the backend schemas exactly.
- Charts read live endpoints, not static arrays.

## Why Recharts

Declarative, small, good enough for the analytics judge screen. No charting
framework with a heavy runtime.

## What to learn

Typed API clients, React data fetching, and keeping UI state minimal by letting the
server be the source of truth.
