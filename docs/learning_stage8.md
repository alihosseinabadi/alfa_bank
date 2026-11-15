# Этап 8 Shared LinUCB

Используйте отдельную PostgreSQL событий из docs/events_stage7.md. Миграции 0001/0002 не изменены; выполнить scripts/migrate_events.py для 0003_reward_ledger. Явно задайте ALFA_EVENTS_DATABASE_URL. Продуктовую БД организаторов не подключать.

Из корня проекта при PYTHONPATH=backend: python scripts/learning_stage8.py tick. Для checkpoint предварительно создайте artifacts/linucb и вызовите python scripts/learning_stage8.py checkpoint. Проверка: python scripts/learning_stage8.py verify. Повреждённый или устаревший checkpoint отвергается; состояние восстанавливается replay из БД. Обработчик использует PostgreSQL advisory transaction lock. Одна зрелая impression вносит один x*xT, изменения reward — только delta b. При провале транзакции повтор безопасен.

Reward-v1: ожидаем 24 часа; max из client click 0.1 и открытия открытого материала 0.15; неподтверждённый intent не является покупкой. Simulated решения и события исключаются. Включать allow_verified_payments нельзя, пока не внедрён настоящий доверенный payment adapter и его проверка; имеющийся PaymentPrincipal сам по себе аутентификацию не делает. Атрибуционное окно по умолчанию семь дней. Награды являются гипотезой, не подтверждением чтения или продаж.

rank_ucb принимает результат prior с применёнными ограничениями, модель из replay или проверенного checkpoint и её state_id. Для полноценного выбора среди кандидатов получите prior до 50 карточек; UCB не восстанавливает те, что были ранее отсечены лимитом. Возвращаемые exploit/explore и state_id сохраняет EventService; вероятность не заявляется. Нужна интеграция в HTTP/auth/frontend и платёжный адаптер. Файлы checkpoint и данные не включать в Git.

Симуляция: PYTHONPATH=backend python scripts/simulate_linucb_stage8.py. Это искусственная нелинейная среда с задержанной наградой, а не оценка продаж, реальных пользователей или качества поиска. Повторное обучение на целевой открытой оценке недопустимо.
