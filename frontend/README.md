# Alfa-Kurs frontend

По умолчанию выдача использует вымышленные примеры из `src/data/demoMaterials.ts`. Поиск по ключевым словам не является TF-IDF или LinUCB и не гарантирует соответствия задаче. Анкета существует только до обновления страницы. Регистрация использует существующий API (`VITE_API_BASE_URL`, по умолчанию `http://127.0.0.1:8000`); свободная задача не отправляется, поскольку локальная схема backend принимает только три готовых значения.

`src/services/recommendations.ts` — граница источника; `src/types/recommendations.ts` — модель интерфейса, не сетевой контракт. `VITE_RECOMMENDATIONS_SOURCE=demo` (или отсутствие переменной) включает демо. `VITE_RECOMMENDATIONS_SOURCE=api` пока намеренно показывает ошибку о неподключённом сервисе, остальные значения — ошибку настройки; демоданные не используются. Переменные Vite задаются перед запуском или сборкой. После согласования контракта заменить API-ветку запросом, проверкой ответа и преобразованием в модель UI.

Локальный снимок `origin/backend` содержит `GET /recommendations/{user_id}` и `POST /interactions/`; префикс развёрнутого сервиса необходимо подтвердить. Код выдачи ссылается на `slate_id`, числовой `impression_id`, `position`, `course`, `reason`, `algorithm`, `model_version`, однако файл схемы рекомендаций пуст, а сервис возвращает первые курсы и ML-заглушки. Схема событий принимает числовой `impression_id` и `event_type` (`click`, `inspect`, `purchase`). Документация расходится с кодом в формате идентификаторов; работа API не проверена.

Для интеграции нужны действующие endpoint и префикс, примеры запроса и ответа с типами и ограничениями полей материалов, правила пустой выдачи и ошибок, идентификаторы показов и события, ссылки, а также поддержка свободной задачи и её обновления. События пока не отправляются, идентификаторы показов не генерируются.

Перед подключением нужно согласовать, как зарегистрированный или анонимный пользователь передаёт задачу: предполагаемый `GET /recommendations/{user_id}` из снимка не принимает свободный текст и зависит от пользователя. После получения действующих примеров добавить адаптер, проверку входящего ответа и соответствующие сценарные тесты; проверить ошибки сети, таймаут, пустую выдачу, повтор и действия с настоящими `impression_id`. В карточках отображаются только абсолютные ссылки HTTP(S). Не использовать неподтверждённые заглушки рейтинга и причины из снимка backend как результаты ML.

`src/services/recommendationController.ts` управляет состояниями выдачи: при новом запросе прежние данные очищаются, запоздалые ответы и ответы после закрытия экрана игнорируются. Тест с управляемыми промисами проверяет эти случаи, ошибку и повтор; это не заменяет браузерную или сквозную проверку настоящего API.

Историческое описание ниже содержит планы, а не сведения о текущей реализации.

React + TypeScript + Vite + Tailwind + Recharts.

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
npm test         # тесты границы источника, ссылок и регистрации с подменой fetch
```

Environment: `VITE_API_BASE_URL=http://127.0.0.1:8000`

## Rules

- Demo data is explicitly labelled; an API failure must not fall back to demo data.
- All API calls go through `services/api.ts`; components never call `fetch` directly.
- UI types do not claim to mirror unconfirmed backend schemas.
- Charts read live endpoints, not static arrays.

## Why Recharts

Declarative, small, good enough for the analytics judge screen. No charting
framework with a heavy runtime.

## What to learn

Typed API clients, React data fetching, and keeping UI state minimal by letting the
server be the source of truth.
