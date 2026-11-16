"""Session-bound HTTP events and strictly isolated simulated learning."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.ml.feature_registry import REGISTRY_HASH
from app.models.events import Decision, DecisionItem, Impression, Interaction, UnattributedClick
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
    assert client.post('/api/v1/events/unattributed-click', headers=headers, json={'event_key': visible['event_key'], 'item_id': item, 'material_key': material}).status_code == 409
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
    # Test-only server command records a synthetic notice and contacts no provider.
    from scripts.demo_test_payment import simulate_payment
    event = simulate_payment(sessions, UUID(card['item_id']), demo=True)
    assert event['impression_id'] == ack['id']
    now = datetime.now(timezone.utc) + timedelta(seconds=3)
    standard = LearningService(sessions)
    demo = learning_service(sessions, demo=True, database_name='alfa_events_test')
    assert standard.tick(now) == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: demo.tick(now), range(2))) == [0, 1]
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
    with pytest.raises(ValueError, match='legacy reward projection'):
        worker.replay()
    assert worker.tick(when) == 1
    assert worker.tick(when) == 0
    assert worker.replay().state_id
    with sessions() as db:
        obs = db.scalars(select(RewardObservation)).one()
        assert obs.reward == 0 and obs.revision == 2
        assert db.get(Interaction, UUID(recorded['id'])).is_free_open is True
        revisions = db.scalars(select(RewardRevision).order_by(RewardRevision.revision)).all()
        assert [r.new_reward for r in revisions] == [.15, 0]
        assert [r.projection_version for r in revisions] == ['legacy-v1', 'verified-free-v2']
        assert revisions[-1].reason == 'legacy_free_revalidation'


def test_legacy_projection_uses_prior_until_worker_revalidates(serving):
    from test_ml_recommendation_provider import actor, request
    from app.schemas.events import ClientAction, VisibilityAck
    provider, sessions = serving
    who = actor()
    issued = provider.recommend(who, request())
    item = issued.items[0]
    events = EventService(sessions)
    impression = events.acknowledge(who, VisibilityAck(event_key=uuid4(), item_id=item.item_id,
        material_key=item.material_key, visible_ms=1200, visible_fraction=.8))
    events.action(who, ClientAction(event_key=uuid4(), item_id=item.item_id,
        material_key=item.material_key, impression_id=impression['id'], kind='click'))
    worker = LearningService(sessions)
    now = datetime.now(timezone.utc) + timedelta(days=2)
    with sessions.begin() as db:
        card = db.get(DecisionItem, item.item_id)
        obs = RewardObservation(id=uuid4(), impression_id=UUID(impression['id']), model_key=worker.model_key,
            registry_hash=REGISTRY_HASH, policy_hash=worker.identity, features=card.snapshot['features']['vector'],
            reward=.15, revision=1, updated_at=now-timedelta(seconds=1))
        db.add(obs); db.flush()
        db.add(RewardRevision(observation_id=obs.id, revision=1, old_reward=None, new_reward=.15,
            recorded_at=now-timedelta(seconds=1), projection_version='legacy-v1'))
    fallback = provider.recommend(who, request())
    assert fallback.message == 'Временно использовано базовое ранжирование.'
    assert worker.tick(now) == 1
    restored = provider.recommend(who, request())
    assert restored.message != 'Временно использовано базовое ранжирование.'
    with sessions() as db:
        assert db.scalars(select(RewardObservation)).one().reward == .1


def test_payment_simulator_rejects_non_demo_and_product_database(serving):
    from scripts.demo_test_payment import simulate_payment
    from app.database.connection import events_engine, events_sessions
    _, sessions = serving
    with pytest.raises(ValueError, match='demo mode'):
        simulate_payment(sessions, uuid4(), demo=False)
    engine = events_engine('postgresql+psycopg://alfa_events:local_events_only@127.0.0.1:55437/alfa_events')
    try:
        with pytest.raises(ValueError, match='isolated'):
            simulate_payment(events_sessions(engine), uuid4(), demo=True)
    finally:
        engine.dispose()


def test_recommendation_replay_cannot_cross_standard_and_demo_mode(serving):
    from test_ml_recommendation_provider import actor, request
    from app.services.recommendation_provider import RequestConflict
    standard, _ = serving
    demo = MLRecommendationProvider(standard.index, standard.manifest, standard.materials,
                                    standard.engine, standard.secret, demo=True)
    first_actor, first_request = actor(), request()
    assert standard.recommend(first_actor, first_request).learning_mode == 'standard'
    with pytest.raises(RequestConflict):
        demo.recommend(first_actor, first_request)
    other_actor, other_request = actor(), request()
    assert demo.recommend(other_actor, other_request).learning_mode == 'test_fast'
    with pytest.raises(RequestConflict):
        standard.recommend(other_actor, other_request)


def test_early_click_is_idempotent_owned_and_never_creates_impression_or_reward(demo_http):
    client, provider, sessions = demo_http
    headers = session(client)
    rec = client.post('/api/v1/recommendations', headers=headers,
        json={'request_key': str(uuid4()), 'task': 'НДС'}).json()
    card = rec['items'][0]
    click = {'event_key': str(uuid4()), 'item_id': card['item_id'], 'material_key': card['material_key']}
    first = client.post('/api/v1/events/unattributed-click', headers=headers, json=click)
    assert first.status_code == 200
    repeat = client.post('/api/v1/events/unattributed-click', headers=headers, json=click)
    assert repeat.json()['id'] == first.json()['id'] and repeat.json()['replayed'] is True
    assert first.json()['impression_id'] is None
    assert client.post('/api/v1/events/visibility', headers=headers, json={**click, 'visible_ms': 1000, 'visible_fraction': .5}).status_code == 409
    with TestClient(client.app) as other:
        assert other.post('/api/v1/events/unattributed-click', headers=session(other), json=click).status_code == 404
    with sessions() as db:
        event = db.scalars(select(UnattributedClick)).one()
        assert event.item_id == UUID(card['item_id']) and event.simulated
        assert db.scalar(select(func.count()).select_from(Impression)) == 0
        assert db.scalar(select(func.count()).select_from(Interaction)) == 0
    demo = learning_service(sessions, demo=True, database_name='alfa_events_test')
    assert demo.tick(datetime.now(timezone.utc) + timedelta(days=2)) == 0


def test_standard_worker_waits_for_maturity_and_restores_without_double_update(store):
    from test_event_storage_stage7 import issue, ack, action
    service, sessions, _ = store
    who, _, _, _, _, item, _ = issue(service, simulated=False, price=0)
    service.acknowledge(who, ack(item))
    service.action(who, action(item, kind='click'))
    worker = LearningService(sessions)
    now = datetime.now(timezone.utc)
    assert worker.tick(now + timedelta(hours=1)) == 0
    assert worker.tick(now + timedelta(hours=25)) == 1
    assert worker.tick(now + timedelta(hours=25)) == 0
    state = worker.replay().state_id
    assert LearningService(sessions).replay().state_id == state
    with sessions() as db:
        assert len(db.scalars(select(RewardObservation)).all()) == 1
        assert len(db.scalars(select(RewardRevision)).all()) == 1
