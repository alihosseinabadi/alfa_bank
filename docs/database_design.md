# Продуктовое хранилище решений показов и событий

Актуальная реализация этапа7 описана в docs/events_stage7.md и
backend/app/models/events.py. Это PostgreSQL с Alembic head0002_event_protocol,
отдельный от источника организаторов.

| Сущность | Ключ и назначение |
|---|---|
| event_actors | UUID actor, kind, anonymous_session_id |
| recommendation_decisions | UUID, actor/request_key unique, контекст и версии, payload hash |
| recommendation_items | UUID, decision/position unique, decision/material unique, exact features/trace |
| recommendation_impressions | UUID, item unique; возникает после visibility acknowledgement |
| interaction_events | UUID, actor/item/impression FK; source/trust, event time, server ingestion |
| event_receipts | actor/event_key unique; тип, fingerprint, ID принятого результата |

Decision/item описывают выдачу, canonical impression описывает принятый
клиентский сигнал видимости. Отдельная запись решения необходима, чтобы не
называть все выданные карточки фактически показанными.
Позиции 1-based. Действия всегда ссылаются на canonical impression.
Один item может иметь несколько легитимных кликов с разными event_key.

Версия events-v1 хранится в решениях, показах, взаимодействиях и receipts.
Покупка уникальна по provider/environment/transaction_key; тестовые события
не смешиваются с реальными. Наград и bandit_state ещё нет.

Признаки не восстанавливаются из изменившегося пользователя/каталога:
хранится точный вектор, маски, значения, версии и scores на момент выдачи.
Текущий event writer — EventService; он дополнительно проверяет составную
связь actor/material/impression. Физические FK не заменяют авторизацию сервиса.

CTR/конверсию не вычислять из всех decision items или необработанного количества
event rows. Сначала нужны настоящая видимость, определённая квалификация действий,
дедупликация бизнес-исходов и явное исключение simulated.
Окна платёжной атрибуции и reward ledger относятся к этапу8.
