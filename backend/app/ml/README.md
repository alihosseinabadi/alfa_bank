# backend/app/ml

Чистые алгоритмы и типизированные контракты. Нет импорта FastAPI, SQLAlchemy,
app.services, app.data_preparation или экспериментов.

| Область | Реализованные модули |
|---|---|
| Профиль и контекст | profile_contracts, profile_policy, user_profile, request_context |
| Поиск | retrieval_contracts, tfidf_retriever, retrieval_baselines, bm25_retriever, e5_retriever |
| Гибрид и цитаты | retrieval_fusion, hybrid_retriever, evidence |
| Метрики поиска | retrieval_metrics |
| Начальное ранжирование | ranking_contracts, ranking_inputs, feature_registry, feature_engineering, prior_ranking |

Единый вход ранжирования — RetrievalBatch, выход — RankingResult.
22 nullable-признака кодируются как bias + значения + маски, всего 45 float32.
Версия pair-features-v1, политика prior-ranking-v1. Старый проектный вектор
из 39 компонент для шести синтетических категорий не используется.

Ранжирование детерминированное, эвристическое, без обучения на наградах.
Частичная оценка качества проведена: docs/quality_stage56.md.
Полезный прирост prior и содержательная приёмка всего поиска не подтверждены.
LinUCB и reward engine ещё не реализованы.

Контракты и формулы: docs/feature_engineering.md.
Запуск, сохранение и ограничения: docs/prior_stage6.md.
Чтение файлов и интеграция находятся за границей ML-модулей:
backend/app/data_preparation/ranking_bundle.py и scripts/rank_materials.py.
