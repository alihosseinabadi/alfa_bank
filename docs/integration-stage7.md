# Этап 7: отчёт о проверке

Проверка 16 ноября 2026 года проведена на коде приложения `906d968`; smoke-скрипт и отчёты добавлены позднее. Среда: Python 3.12.3, Node 18.19.1, npm 9.2.0, Docker 29.3.0, PostgreSQL 16. Каталог и поисковый индекс — локальные приватные артефакты, отсутствующие в Git. Подробности отдельных сценариев и их ограничения: [сквозные проверки](stage7-e2e.md), [оценка качества](stage7-quality.md).

## Автоматические проверки

Подготовьте тестовые БД согласно [этапу 2](integration-stage2.md) и Python-зависимости. Значения ниже — локальные тестовые примеры; используйте свои учётные данные. Обе тестовые БД должны быть изолированы от рабочих.

```bash
export DATABASE_URL='postgresql+psycopg://alfakurs:change_me@127.0.0.1:55438/alfakurs'
export ALFA_EVENTS_TEST_DATABASE_URL='postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:55437/alfa_events_test'
export ALFA_PRODUCT_TEST_DATABASE_URL='postgresql+psycopg://alfakurs:change_me@127.0.0.1:55438/alfa_product_test'
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pytest backend/tests -q -rs --disable-warnings --maxfail=2
npm --prefix frontend test
npm --prefix frontend run build
```

Результат: **277 passed, 2 warnings**, пропусков нет; frontend **21 passed**, сборка успешна. Независимый критик дополнительно выполнил тесты событий и конкурентного доступа к PostgreSQL: 37 passed, 2 warnings. Тесты проверяют повторную доставку, параллельные операции, транзакции, обработку некорректных запросов, восстановление модели после воссоздания провайдера и fallback. Дополнительно выполнен перезапуск отдельного процесса backend: тестовый worker обновил награду конкретного показа, модель восстановила состояние, а повторный запрос вернул сохранённый ответ; команда приведена в отчёте сквозных проверок.

## Миграции на пустых базах

Для проверки поднят отдельный временный PostgreSQL 16 без постоянного тома на локальном порту 55449; созданы две новые пустые базы, после проверки контейнер остановлен. Не используйте эти команды против рабочих БД:

```bash
docker run -d --rm --name alfa-stage7-migrations -e POSTGRES_PASSWORD=stage7_local -p 127.0.0.1:55449:5432 postgres:16-alpine
# Дождитесь готовности pg_isready.
docker exec alfa-stage7-migrations createdb -U postgres alfa_product_test
docker exec alfa-stage7-migrations createdb -U postgres alfa_events_test
DATABASE_URL='postgresql+psycopg://postgres:stage7_local@127.0.0.1:55449/alfa_product_test' python -m alembic -c backend/product-alembic.ini upgrade head
ALFA_EVENTS_DATABASE_URL='postgresql+psycopg://postgres:stage7_local@127.0.0.1:55449/alfa_events_test' python scripts/migrate_events.py
DATABASE_URL='postgresql+psycopg://postgres:stage7_local@127.0.0.1:55449/alfa_product_test' python -m alembic -c backend/product-alembic.ini check
docker stop alfa-stage7-migrations
```

Обе цепочки успешно применены, `alembic check` продуктовой схемы: `No new upgrade operations detected`. Проверка событийной схемы относительно metadata входит в автоматические тесты.

## Что осталось непроверенным

На реальном каталоге два подходящих smoke-запроса дали по одной карточке; несколько допустимых карточек не подтверждены. Сетевой браузерный прогон этапа 6 и текущий TestClient smoke — разные проверки; последний не проверяет сеть и внешние сайты. Подтверждение фактического открытия бесплатного материала отсутствует: endpoint `material_open` возвращает 503, платёжного адаптера нет. Нельзя считать это завершённым пользовательским сценарием. Доставка браузерных событий при закрытии вкладки не гарантирована.

Новому пулу качества не назначены оценки релевантности; историческая приватная разметка недоступна для пересчёта, E5 не сопоставлялся из-за неподтверждённой совместимости индекса. Метрики конверсии и продаж не измерялись. Независимая оценка критика — **7/10**, с перечисленными ограничениями.
