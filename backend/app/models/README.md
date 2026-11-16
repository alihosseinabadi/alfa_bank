# Модели продуктового хранилища

Реализованы app/models/events.py: event_actors, recommendation_decisions,
recommendation_items, recommendation_impressions, interaction_events, event_receipts.
Точные назначения и ограничения: docs/events_stage7.md.

Выданное решение не является показом. recommendation_impressions — единственная
canonical запись клиентского visibility acknowledgement для выданного item.
Сырые события связаны с ней. Признаки на момент решения сохраняются в item.snapshot.
Повторы блокируются ключами actor/request_key, actor/event_key и provider/environment/transaction_key.

Миграции управляются Alembic. create_all в продуктовом запуске не используется.
Таблиц bandit_state/reward ledger пока нет. Старые проектные users/courses не
являются копией базы организаторов и этим этапом не реализованы.
