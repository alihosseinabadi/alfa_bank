# Этап 7: сквозные проверки

## Реальный каталог, тестовые действия

Проверка `scripts/stage7_http_smoke.py` использует FastAPI TestClient внутри процесса, реальный локальный каталог и индекс и исключительно событийную БД `alfa_events_test`. Пользователь и его действия синтетические, режим обучения — `test_fast`; тест не доказывает работу сети, внешнего сайта или реального платежа. Требуются подготовленные локальные артефакты и миграции по [этапу 5](integration-stage5.md). Пример запуска из корня проекта:

```bash
export DATABASE_URL='postgresql+psycopg://alfakurs:change_me@127.0.0.1:55438/alfakurs'
export ALFA_EVENTS_DATABASE_URL='postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:55437/alfa_events_test'
export ALFA_SESSION_SECRET='test-secret-stage-seven-xxxxxxxxxxxxxxxxxxxxxxxxxxxx'
export ALFA_SESSION_COOKIE_SECURE=false ALFA_RECOMMENDATIONS_ENABLED=true ALFA_DEMO_FAST_LEARNING=true
PYTHONPATH=backend python scripts/stage7_http_smoke.py
```

16 ноября 2026: новая анонимная сессия; запрос про НДС с ограничением article — `matched`, одна карточка, статус ссылки `unknown`; другая задача про клиентов — `matched`, одна карточка; запрос вне тематики — `needs_clarification`, пустой список; запрос НДС с ограничением podcast — `needs_clarification`, пустой список. Повтор идентичного запроса вернул идентичный ответ, повтор с изменённым текстом — 409. Видимость и клик подтверждены; повтор события вернул тот же ID, `replayed=true`. Некорректный запрос вернул 422. Попытка клиентского `material_open` вернула 503: это ожидаемое ограничение, доверенного подтверждения открытия внешнего материала нет. Непроверенные ссылки не объявляются рабочими.

На этих двух подходящих запросах получена одна карточка, поэтому проверка выдачи нескольких допустимых карточек на реальном каталоге **не подтверждена**. Размер подборки ограничен действующей политикой, искусственное заполнение не проводилось. Эта проверка не выполняет реальное открытие бесплатного материала.

## Изолированные HTTP- и PostgreSQL-тесты

```bash
export DATABASE_URL='postgresql+psycopg://alfakurs:change_me@127.0.0.1:55438/alfakurs'
export ALFA_EVENTS_TEST_DATABASE_URL='postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:55437/alfa_events_test'
export ALFA_PRODUCT_TEST_DATABASE_URL='postgresql+psycopg://alfakurs:change_me@127.0.0.1:55438/alfa_product_test'
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m pytest backend/tests/test_stage5_events.py backend/tests/test_ml_recommendation_provider.py backend/tests/test_recommendation_api_contract.py -q -rs --disable-warnings --maxfail=1
```

Результат: **26 passed, 2 warnings**. Эти тесты используют искусственный каталог и изолированные схемы PostgreSQL: проверяются ограничения формата и цены, неизвестная ссылка, пустой результат, вне тематики, недоступный каталог и prior-fallback при сбое модели, конкурентные повторы и rollback, повтор после воссоздания провайдера, подтверждение видимости, клик, идемпотентность, изоляция сессии, test-fast обновление модели и запрет фиктивной покупки. Проверка воссоздания провайдера не заменяет перезапуск отдельного процесса. Тестовую покупку нельзя считать реальным платежом или эффектом на продажи.

## Перезапуск процесса и состояние модели

В том же тестовом окружении запущено:

```bash
PYTHONPATH=backend python scripts/stage7_restart_smoke.py
```

Скрипт запускает отдельный локальный uvicorn на случайном свободном порту, получает реальную рекомендацию из каталога, фиксирует синтетические видимость и клик, затем запускает отдельный тестовый worker. Для конкретного показа в БД проверена награда 0,1, ID состояния изменился. После остановки и повторного запуска uvicorn тот же запрос с прежними cookie вернул сохранённый ответ; отдельный процесс replay восстановил идентичный ID состояния, новый запрос обслужен без сообщения о fallback. Результат: `Updated reward observations: 1`, `PASS`. Все созданные скриптом процессы backend завершаются в `finally`. Это тестовая симуляция, а не реальное обучение на покупке.
