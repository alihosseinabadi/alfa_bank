"""Record an explicitly simulated payment notice only in the isolated demo DB.

No payment provider is contacted and this notice never counts as revenue or as
reward for the demo model. An existing simulated decision and impression are
required. This tool is deliberately not exposed as an HTTP endpoint.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import UUID, uuid4

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import get_settings
from app.database.connection import events_engine, events_sessions
from app.models.events import Actor, Decision, DecisionItem, Impression
from app.schemas.events import PaymentNotice, PaymentPrincipal, TrustedActor
from app.services.event_service import EventService


def simulate_payment(sessions, item_id, *, demo=False):
    bind = sessions.kw.get('bind')
    if not demo or bind is None or bind.url.database != 'alfa_events_test':
        raise ValueError('Test payment requires demo mode and isolated alfa_events_test')
    with sessions() as db:
        record = db.execute(select(DecisionItem, Decision, Actor, Impression)
            .join(Decision, Decision.id == DecisionItem.decision_id)
            .join(Actor, Actor.id == Decision.actor_id)
            .join(Impression, Impression.item_id == DecisionItem.id)
            .where(DecisionItem.id == item_id)).first()
        if record is None:
            raise ValueError('A simulated issued item with a confirmed impression is required')
        item, decision, actor, impression = record
        if not decision.simulated:
            raise ValueError('Only simulated decisions can receive a test payment')
        principal = TrustedActor(actor_id=actor.id, session_id=decision.session_id, kind=actor.kind)
        notice = PaymentNotice(event_key=uuid4(), item_id=item.id, material_key=item.material_key,
            impression_id=impression.id, transaction_key='demo-' + uuid4().hex,
            amount='1.00', currency='RUB', occurred_at=datetime.now(timezone.utc))
    return EventService(sessions).purchase(principal, notice, PaymentPrincipal(provider='demo', environment='test'))


def main():
    parser = argparse.ArgumentParser(description='SIMULATION ONLY: no real payment is made.')
    parser.add_argument('--item-id', required=True, type=UUID, help='UUID of a simulated item with an impression')
    args = parser.parse_args()
    if not get_settings().demo_fast_learning:
        raise ValueError('Set ALFA_DEMO_FAST_LEARNING=true for this test-only command')
    engine = events_engine()
    try:
        if engine.url.database != 'alfa_events_test':
            raise ValueError('Test payment requires isolated alfa_events_test')
        receipt = simulate_payment(events_sessions(engine), args.item_id, demo=get_settings().demo_fast_learning)
        print('TEST ONLY: simulated payment notice recorded; no real purchase or reward.')
        print('Event ID:', receipt['id'])
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
