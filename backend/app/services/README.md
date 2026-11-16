# Сервисы

EventService в event_service.py реализует транзакционные use cases этапа7:
issue, acknowledge, action, purchase. Вход — подготовленные RankingResult,
RequestContext, RetrievalBatch и доверенный серверный actor.
Политика дедупликации, доверия и запуска: docs/events_stage7.md.

Транзакции и actor/material/impression binding принадлежат сервису.
Покупка с клиента остаётся purchase_intent; подтверждение принимает только
отдельный внутренний серверный путь. Auth/проверка подписи провайдера ещё не подключены.
Сервис не рассчитывает reward, не обновляет LinUCB и не пересчитывает профиль.
Рекомендации подготавливаются существующим ML/файловым pipeline.
HTTP orchestration и аналитика остаются последующими задачами.
