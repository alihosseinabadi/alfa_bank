# Alfa-Kurs frontend

По умолчанию выдача использует вымышленные примеры из `src/data/demoMaterials.ts`. Поиск по ключевым словам не является TF-IDF или LinUCB и не гарантирует соответствия задаче. Анкета существует только до обновления страницы. Регистрация нацелена на ветку `backend` (снимок `d36f2d1`), но её работа с сервером ещё не проверена. Модель БД требует `current_goal`, а схема принимает только три готовых варианта: поэтому до исправления backend регистрация требует выбрать один из них. Свободный текст остаётся в интерфейсе и на сервер не отправляется. Backend также пока не сохраняет `experience`, хотя принимает его в запросе.

`src/services/recommendations.ts` — граница источника; `src/types/recommendations.ts` — модель интерфейса, не сетевой контракт. `VITE_RECOMMENDATIONS_SOURCE=demo` (или отсутствие переменной) включает демо. `VITE_RECOMMENDATIONS_SOURCE=api` пока намеренно показывает ошибку о неподключённом сервисе, остальные значения — ошибку настройки; демоданные не используются. Переменные Vite задаются перед запуском или сборкой. После согласования контракта заменить API-ветку запросом, проверкой ответа и преобразованием в модель UI.

Ветка `backend` содержит `GET /api/v1/recommendations/{user_id}` и `POST /api/v1/interactions/`, но файл `backend/app/schemas/recommendation.py` пуст, тогда как приложение импортирует из него классы. Выдача берёт первые курсы из БД и содержит заглушки алгоритма и причины; это не поиск ML. Такой сервер нельзя считать работающим до исправления и проверки. Backend выдаёт числовые `impression_id` при получении выдачи.

Актуальный проверенный на GitHub `ml` — `7ec09e5` от 14 ноября: поиск TF-IDF/BM25 и экспериментальный гибрид, prior, внутренний shared LinUCB, slate и журнал событий. Новая оркестрация является внутренним Python-сервисом и возвращает отдельные `decision`, `result` и `fallback_reason`; HTTP/auth и интеграции с выбранной веткой `backend` нет. Документация отдельных этапов и корневой README могут отставать от кода. Локальные тесты новых ML-этапов в этом рабочем дереве не запускались. Модели `RankingResult` и `VisibilityAck` не являются схемами API выбранной серверной ветки. В ML показ возникает после подтверждения видимости, `item_id`/`impression_id` — UUID; в backend — другая модель. Нельзя смешивать их или генерировать идентификаторы во фронтенде.

`src/services/stage6Adapter.ts` проверяет и преобразует публичные поля Python-моделей `prior-ranking-v1`, `shared-linucb-ranking-v1` и `epsilon-diverse-slate-v1/v2` в карточки, включая статусы уточнения, типы, доступ и осторожное отображение цен/ссылок. Это подготовительный адаптер для согласования: он принимает внутренний объект RankingResult, а не ответ оркестратора, не подключён к серверу, не объявляет HTTP-контракт и не обрабатывает события. Приватные оценки, вероятности, seed и массив `eligible_candidates` в UI не выводятся. Нулевая цена материала по подписке не отображается как бесплатный доступ.

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

Прокси Vite выключен по умолчанию, чтобы случайно не отправить данные другому приложению на занятом порту. Для разработки задайте `VITE_API_PROXY_TARGET` адресом проверенного backend (например, `http://127.0.0.1:8000`) и перезапустите Vite. `VITE_API_BASE_URL` опционально задаёт origin API напрямую — тогда backend должен разрешать CORS. При production-сборке нужен reverse proxy для `/api` или настроенный origin с CORS: dev-прокси в собранном приложении не работает.

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
