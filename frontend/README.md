# Alfa-Kurs frontend

Основной режим подключается к API рекомендаций; `VITE_RECOMMENDATIONS_SOURCE=demo` включает отдельно обозначенные вымышленные примеры. Ошибка API не подменяется демоданными. Анкета и ключ повторного запроса сохраняются в `sessionStorage` текущей вкладки, если браузер разрешает хранение; при закрытии вкладки восстановление не гарантируется. На экране аналитики могут отображаться демонстрационные данные.

Запустите backend и worker по [инструкции этапа 5](../docs/integration-stage5.md), установите зависимости и запустите frontend:

```bash
npm --prefix frontend install
VITE_API_BASE_URL=http://127.0.0.1:8000 npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
npm --prefix frontend test
npm --prefix frontend run build
```

Разрешите origin frontend в `API_CORS_ORIGINS`. Корневой `.env.example` не загружается Vite автоматически: задайте переменные в окружении или в файле окружения внутри `frontend`. Вместо `VITE_API_BASE_URL` можно настроить `VITE_API_PROXY_TARGET` для dev-прокси; в собранном приложении нужен reverse proxy или API origin с CORS. Для демонстрационных примеров задайте `VITE_RECOMMENDATIONS_SOURCE=demo` перед запуском или сборкой.

Контракт API описан в [recommendation-api-v1.md](../docs/recommendation-api-v1.md), ограничения событий и тестового обучения — в инструкции этапа 5. Подтверждение реальной покупки и внешнего открытия материала пока не подключено.
