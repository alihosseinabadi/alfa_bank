"""Session-bound HTTP events and strictly isolated simulated learning."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.ml.feature_registry import REGISTRY_HASH
from app.models.events import Decision, DecisionItem, Impression, Interaction
from app.models.learning import RewardObservation, RewardRevision
from app.schemas.events import PaymentNotice, PaymentPrincipal
from app.services.event_service import EventService
from app.services.learning_configuration import DEMO_MODEL_KEY, learning_service
from app.services.learning_service import LearningService
from app.services.ml_recommendation_provider import MLRecommendationProvider
from test_event_storage_stage7 import store
from test_ml_recommendation_provider import serving


def session(client):
    response = client.post('/api/v1/session')
    assert response.status_code == 200
    return {'X-CSRF-Token': response.json()['csrf_token']}


@pytest.fixture
def demo_http(serving, monkeypatch):
    base, sessions = serving
    provider = MLRecommendationProvider(base.index, base.manifest, base.materials, base.engine, base.secret, demo=True)
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@127.0.0.1/alfakurs')
    monkeypatch.setenv('ALFA_SESSION_SECRET', 'test-secret-' + 'x' * 32)
    monkeypatch.setenv('ALFA_SESSION_COOKIE_SECURE', 'false')
    monkeypatch.setenv('ALFA_RECOMMENDATIONS_ENABLED', 'false')
    get_settings.cache_clear()
    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        app.state.recommendation_provider = provider
        yield client, provider, sessions
    get_settings.cache_clear()


def test_http_visibility_actions_idempotency_and_session_ownership(demo_http):
    client, provider, sessions = demo_http
    headers = session(client)
    rec = client.post('/api/v1/recommendations', headers=headers,
        json={'request_key': str(uuid4()), 'task': 'НДС', 'constraints': {'formats': ['article']}})
    assert rec.status_code == 200, rec.text
    assert rec.json()['learning_mode'] == 'test_fast'
    card = rec.json()['items'][0]
    item, material = card['item_id'], card['material_key']
    action = {'event_key': str(uuid4()), 'item_id': item, 'material_key': material, 'kind': 'click'}
    assert client.post('/api/v1/events/action', headers=headers, json=action).status_code == 409
    with TestClient(client.app) as other:
        other_headers = session(other)
        assert other.post('/api/v1/events/visibility', headers=other_headers, json={
            'event_key': str(uuid4()), 'item_id': item, 'material_key': material,
            'visible_ms': 1000, 'visible_fraction': 0.5}).status_code == 404
    visible = {'event_key': str(uuid4()), 'item_id': item, 'material_key': material,
               'visible_ms': 1100, 'visible_fraction': .6}
    response = client.post('/api/v1/events/visibility', headers=headers, json=visible)
    assert response.status_code == 200
    impression = response.json()['id']
    assert client.post('/api/v1/events/visibility', headers=headers, json=visible).json()['id'] == impression
    assert client.post('/api/v1/events/visibility', headers=headers, json={**visible, 'visible_ms': 1300}).status_code == 409
    assert client.post('/api/v1/events/visibility', headers=headers, json={**visible, 'event_key': str(uuid4()), 'visible_ms': 999}).status_code == 422
    action['impression_id'] = impression
    first = client.post('/api/v1/events/action', headers=headers, json=action)
    assert first.status_code == 200
    repeat = client.post('/api/v1/events/action', headers=headers, json=action)
    assert repeat.json()['id'] == first.json()['id'] and repeat.json()['replayed'] is True
    assert client.post('/api/v1/events/action', headers=headers, json={**action, 'kind': 'purchase_intent'}).status_code == 409
    assert client.post('/api/v1/events/action', headers=headers, json={**action, 'event_key': str(uuid4()), 'kind': 'purchase_confirmed'}).status_code == 422
    assert client.post('/api/v1/events/action', headers=headers, json={**action, 'event_key': str(uuid4()), 'impression_id': str(uuid4())}).status_code == 404
    opened = client.post('/api/v1/events/action', headers=headers, json={**action, 'event_key': str(uuid4()), 'kind': 'material_open'})
    assert opened.status_code == 503  # external page opening is not verified
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Impression)) == 1
        events = db.scalars(select(Interaction)).all()
        assert len(events) == 1 and events[0].kind == 'click' and events[0].simulated


def test_demo_learning_is_separate_and_simulated_purchase_never_rewards(demo_http):
    client, provider, sessions = demo_http
    headers = session(client)
    out = client.post('/api/v1/recommendations', headers=headers,
        json={'request_key': str(uuid4()), 'task': 'НДС'}).json()
    card = out['items'][0]
    ack = client.post('/api/v1/events/visibility', headers=headers, json={
        'event_key': str(uuid4()), 'item_id': card['item_id'], 'material_key': card['material_key'],
        'visible_ms': 1200, 'visible_fraction': .8}).json()
    assert client.post('/api/v1/events/action', headers=headers, json={
        'event_key': str(uuid4()), 'item_id': card['item_id'], 'material_key': card['material_key'],
        'impression_id': ack['id'], 'kind': 'click'}).status_code == 200
    # This is a synthetic server-to-server test notice, never a real payment.
    from app.core.anonymous_session import read_cookie
    actor = read_cookie(get_settings().session_secret, client.cookies.get('alfa_anon_session'))
    event = EventService(sessions).purchase(actor, PaymentNotice(event_key=uuid4(), item_id=card['item_id'],
        material_key=card['material_key'], impression_id=ack['id'], transaction_key='test-' + uuid4().hex,
        amount='100.00', currency='RUB', occurred_at=datetime.now(timezone.utc)), PaymentPrincipal(provider='test', environment='test'))
    assert event['impression_id'] == ack['id']
    now = datetime.now(timezone.utc) + timedelta(seconds=3)
    standard = LearningService(sessions)
    demo = learning_service(sessions, demo=True, database_name='alfa_events_test')
    assert standard.tick(now) == 0
    assert demo.tick(now) == 1
    assert demo.tick(now) == 0
    with sessions() as db:
        obs = db.scalars(select(RewardObservation)).one()
        assert obs.model_key == DEMO_MODEL_KEY and obs.reward == .1
        assert len(db.scalars(select(RewardRevision)).all()) == 1
        assert all(e.simulated for e in db.scalars(select(Interaction)).all())
    updated = demo.replay()
    assert updated.state_id != provider._model_cache.state_id
    provider._model_cache = None
    with sessions.begin() as db:
        assert provider._model(db).state_id == updated.state_id


def test_demo_configuration_refuses_product_database(serving):
    provider, sessions = serving
    with pytest.raises(ValueError, match='isolated'):
        learning_service(sessions, demo=True, database_name='alfa_events')
    fake = type('Engine', (), {'url': type('Url', (), {'database': 'alfa_events'})()})()
    with pytest.raises(ValueError, match='isolated'):
        MLRecommendationProvider(provider.index, provider.manifest, provider.materials, fake, provider.secret, demo=True)


def test_old_false_free_claim_is_revised_without_rewriting_event(store):
    from test_event_storage_stage7 import issue, ack, action
    service, sessions, _ = store
    a, _, _, _, _, item, _ = issue(service, simulated=False, price=None)
    receipt = service.acknowledge(a, ack(item))
    recorded = service.action(a, action(item, kind='material_open'))
    worker = LearningService(sessions)
    when = datetime.now(timezone.utc) + timedelta(days=2)
    with sessions.begin() as db:
        impression = db.get(Impression, UUID(receipt['id']))
        event = db.get(Interaction, UUID(recorded['id']))
        event.is_free_open = True  # simulate an immutable event produced by the old version
        decision_item = db.get(DecisionItem, UUID(item['item_id']))
        obs = RewardObservation(id=uuid4(), impression_id=impression.id, model_key=worker.model_key,
            registry_hash=REGISTRY_HASH, policy_hash=worker.identity, features=decision_item.snapshot['features']['vector'],
            reward=.15, revision=1, updated_at=when - timedelta(seconds=1))
        db.add(obs); db.flush()
        db.add(RewardRevision(observation_id=obs.id, revision=1, old_reward=None, new_reward=.15, recorded_at=when-timedelta(seconds=1), projection_version='legacy-v1'))
    assert worker.tick(when) == 1
    assert worker.tick(when) == 0
    with sessions() as db:
        obs = db.scalars(select(RewardObservation)).one()
        assert obs.reward == 0 and obs.revision == 2
        assert db.get(Interaction, UUID(recorded['id'])).is_free_open is True
        revisions = db.scalars(select(RewardRevision).order_by(RewardRevision.revision)).all()
        assert [r.new_reward for r in revisions] == [.15, 0]
        assert [r.projection_version for r in revisions] == ['legacy-v1', 'verified-free-v2']
        assert revisions[-1].reason == 'legacy_free_revalidation'
