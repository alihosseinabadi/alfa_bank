# Product events PostgreSQL

connection.py создаёт engine только из явного ALFA_EVENTS_DATABASE_URL.
Разрешены отдельные alfa_events/alfa_events_test, драйвер postgresql+psycopg.
Нет fallback на исходную базу организаторов или общий DATABASE_URL.
events_sessions создаёт sessionmaker; EventService владеет begin/commit/rollback.

base.py: общий DeclarativeBase. Схема создаётся явными Alembic-миграциями,
не create_all. Docker и команды: docs/events_stage7.md.
Тестовые данные изолированы в новой базе и случайных схемах.
