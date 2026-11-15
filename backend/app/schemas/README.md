# Контракты событий

events.py содержит строгие Pydantic DTO с запретом лишних полей.
VisibilityAck: сообщение о видимости; ClientAction: click/material_open/purchase_intent.
PaymentNotice: отдельное серверное сообщение о транзакции.
TrustedActor и PaymentPrincipal — внутренние principals, не клиентское тело.
Полные поля и правила: docs/events_stage7.md.

Нельзя задать reward, actor_id или подтверждённую покупку через ClientAction.
client_time требует timezone и не выдаётся за доказанное время поведения.
API/Frontend ещё должны связать эти контракты с аутентифицированным запросом
и настоящим visibility observer.
