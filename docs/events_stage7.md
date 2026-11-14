# Этап 7 Решения показы и события MVP

Реализован отдельный PostgreSQL event store. Запись решения, клиентское
подтверждение видимости и действие — разные операции. Наград, LinUCB и
обновления профиля этим этапом не добавлено. Содержательные ограничения поиска
из docs/quality_stage56.md остаются открытыми.

## Запуск

Из корня репозитория в окружении conda alpha:

```bash
docker compose -f scripts/events.compose.yml up -d --wait
export ALFA_EVENTS_DATABASE_URL='postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:55437/alfa_events'
python scripts/migrate_events.py
python scripts/demo_event_flow.py issue
python scripts/demo_event_flow.py actions
python scripts/demo_event_flow.py actions
python scripts/demo_event_flow.py verify
```

Пароль выше — значение для изолированного локального демо, задаётся также
ALFA_EVENTS_PASSWORD в Compose. Продуктовая база alfa_events и отдельная тестовая
alfa_events_test работают на 127.0.0.1:55437. Архив/том исходной базы не монтируются.
Существующий docker-compose.yml и базу организаторов новый сервис не меняет.

Демо использует настоящий каталог и ранжирование, но новый искусственный actor,
синтетические действия и явно тестовый платёж. В stdout только агрегаты.
Приватный receipt: reports/stage7_demo_v1_receipt.json.
Повторный запуск использует прежние ключи; не создаёт новый показ/платёж.
Для нового независимого демо задайте другой --receipt под reports/artifacts.

Для проверки сохранности можно перезапустить только продуктовый контейнер:

```bash
docker compose -f scripts/events.compose.yml restart db
docker compose -f scripts/events.compose.yml up -d --wait
python scripts/demo_event_flow.py verify
```

## Реализованные файлы и вызовы

- app/schemas/events.py: VisibilityAck, ClientAction, PaymentNotice и серверные principals.
- app/models/events.py: шесть таблиц.
- app/database/connection.py: явный URL только для отдельных продуктовых/тестовых БД.
- app/services/event_service.py: транзакции и проверки.
- backend/migrations: явные Alembic-миграции, head0002_event_protocol.
- scripts/demo_event_flow.py: раздельные процессы демо.
- backend/tests/test_event_storage_stage7.py: настоящие PostgreSQL-тесты.

Сервис получает sessionmaker и доверенный серверный TrustedActor.
issue принимает request_key, RankingResult, RequestContext и обязательный
retrieval_batch. Последний нужен для точного исходного raw score, включая
fused score, которого нет отдельно в RankedMaterial. Проверяются provenance,
первоначальный rank, channel/rank/raw_score/chunk/source_ids.
Снимок не пересчитывается при клике.

## Сущности

| Таблица | Значение |
|---|---|
| event_actors | Псевдоним actor и тип; anonymous привязан к своей session |
| recommendation_decisions | Выданное решение; уникальный actor + request_key |
| recommendation_items | Позиция и материал; точные признаки, версии и исходный trace |
| recommendation_impressions | Один первый принятый visibility acknowledgement на item |
| interaction_events | Сырые клики, открытия, намерения и серверные подтверждения |
| event_receipts | Уникальный actor + event_key и fingerprint принятого сообщения |

Decision и item не являются показами. Единственный canonical impression
возникает только после acknowledgement. Позиции 1-based; материал в slate уникален.
Отдельная запись решения не дублирует факт показа, а фиксирует то, что было выдано.

Хранятся 45-компонентный vector с масками, nullable values, registry hash,
версии профиля/каталога/индекса/политик, исходные channel scores и retrieval score,
prior score и компоненты, query_source/history_weight и ограничения контекста.
Raw query, email, IP, имена, содержимое уроков и произвольный payload не копируются.
В контексте оставлен query_sha256. Это псевдонимизация, не полная анонимизация:
короткие запросы могут угадываться словарём. Всё хранилище остаётся приватным.
Версия протокола events-v1 сохраняется отдельно от версии признаков/ранжировщика.
Политика детерминированная; action_probability=null, данных для IPS/OPE нет.

## Показ и события

VisibilityAck принимает event_key, item_id, material_key, необязательный aware
client_time, visible_ms>=1000 и visible_fraction>=0.5.
Это сообщение клиента о выполнении порога, не серверное доказательство чтения.
Настоящий frontend observer и аутентифицированный HTTP endpoint ещё предстоят.

ClientAction разрешает click, material_open, purchase_intent. Поля actor_id,
reward, source и purchase_confirmed в клиентском теле не допускаются.
impression_id необязателен на входе: можно разрешить единственный impression
строго по выданному item_id. Если ID передан, он должен совпасть.
В БД interaction всегда связан с ненулевым canonical impression.

До acknowledgement действие отвергается VisibilityRequired без записи.
Клиент должен повторить исходное сообщение с прежним event_key после ack.
Сервис не выдумывает показ из клика. Другой event_key означает новое сырое
действие, которое не обязательно станет новой наградой на этапе 8.

is_free_open вычисляется по access_type=Открытый. Нулевая listed_price
подписочного курса не делает открытие бесплатным. Любое клиентское открытие
остаётся client_reported и qualified_use=false.

PaymentNotice обрабатывается только отдельным серверным purchase-вызовом
с PaymentPrincipal. Provider/environment/transaction_key уникальны во всей базе.
Повтор с новым event_key и той же транзакцией возвращает прежнее событие;
изменённый actor/item/amount/currency вызывает конфликт.
Production-приём выключен по умолчанию. Тестовая транзакция всегда simulated.
Доверенный DTO сам не проверяет подпись шлюза: настоящий платёжный адаптер
и его аутентификация должны быть добавлены при интеграции.
Платёжная атрибуция, награды, ledger и maturity остаются этапом 8.

## Повторы время и транзакции

Одинаковые ID и содержимое возвращают тот же resource ID с той же формой ответа;
поменявшееся содержимое — EventConflict. UTC и Decimal нормализуются перед hash.
Поздний повтор ранее принятого сообщения возвращается до новой проверки возраста.
Уникальные ключи БД, row lock actor и transaction advisory lock платежа защищают
от конкурентных дублей. Разные actor не могут присвоить одну транзакцию.

Клиентское время допускается от now-7days до now+5minutes; серверное время
ingestion хранится отдельно. Для provider timestamp предел30days.
Это границы приёма сообщения, не окно атрибуции и не доказательство времени действия.
Анонимный и авторизованный actor автоматически не объединяются.
TrustedActor должен приходить из сервера, не из клиентского JSON:
полного auth/identity сервиса этот этап не реализует.

Сервис проверяет actor/material/impression binding. Самостоятельные SQL FK
не обеспечивают всю составную согласованность при обходном INSERT.
MVP рассчитан на единственный writer через сервис; ужесточение DB ролей/составных
FK возможно при интеграции. Сбой внутри транзакции откатывает весь slate.

## Проверка и границы

```bash
export ALFA_EVENTS_TEST_DATABASE_URL='postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:55437/alfa_events_test'
python -m pytest backend/tests -q
```

Тесты создают только собственные stage7_test_UUID schemas в явно указанной
alfa_events_test и удаляют только их. Без переменной PostgreSQL-тесты пропускаются:
такой прогон не заменяет полную проверку конкурентности.

Не реализованы: реальный frontend visibility, HTTP/auth, проверка подписи
платёжного шлюза, автоматическое обновление профилей, reward ledger и обучение.
Успешный event-store не исправляет известные OOD/морфологические ошибки поиска
и не доказывает рост продаж.
