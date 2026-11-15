"""Synthetic end-to-end serving tests using an isolated real PostgreSQL schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.ml.tfidf_retriever import TfidfRetriever
from app.models.events import Decision, DecisionItem, Impression
from app.models.serving import ServingRequest
from app.schemas.events import ClientAction, TrustedActor, VisibilityAck
from app.schemas.recommendation import RecommendationRequest
from app.services.event_service import EventService
from app.services.learning_service import LearningService
from app.services.ml_recommendation_provider import MLRecommendationProvider
from app.services.recommendation_provider import ProviderUnavailable, RequestConflict
from test_event_storage_stage7 import store
from test_prior_ranking_stage6 import chunk, material


@pytest.fixture
def serving(store):
    _, sessions, engine = store
    materials = [material('a', title='НДС для бизнеса', duration_minutes=15),
                 material('b', title='Налоговый учёт', item_type='course', access_type='По подписке', listed_price=0)]
    rows = [chunk('a'), chunk('b')]
    index = TfidfRetriever().fit(materials, rows)
    provider = MLRecommendationProvider(index, {'bundle_id': 'index', 'catalog_bundle_id': 'catalog'},
                                        materials, engine, 'test-secret-' + 'x' * 32)
    return provider, sessions


def actor():
    identity = uuid4()
    return TrustedActor(actor_id=identity, session_id=identity, kind='anonymous')


def request(**changes):
    return RecommendationRequest.model_validate({'request_key': str(uuid4()), 'task': 'НДС', **changes})


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_real_pipeline_writes_decision_not_impression_and_returns_safe_fields(serving):
    provider, sessions = serving
    a, q = actor(), request(constraints={'formats': ['article'], 'budget_preference': 'free_only', 'available_time_minutes': 15})
    out = provider.recommend(a, q)
    assert out.status == 'matched' and len(out.items) == 1
    assert out.items[0].material_key == 'a' and out.items[0].link_status == 'unknown'
    assert out.items[0].format == 'article' and out.items[0].access_type == 'Открытый'
    assert provider.recommend(a, q) == out
    payload = out.model_dump(mode='json')
    assert 'seed' not in payload and 'features' not in payload['items'][0]
    with sessions() as db:
        assert count(db, Decision) == count(db, DecisionItem) == count(db, ServingRequest) == 1
        assert count(db, Impression) == 0
    with pytest.raises(RequestConflict):
        provider.recommend(a, q.model_copy(update={'task': 'другое'}))
    # Identical keys under distinct server-issued identities do not collide.
    assert provider.recommend(actor(), q).decision_id != out.decision_id


def test_subscription_zero_price_is_not_presented_as_confirmed_free(serving):
    provider, _ = serving
    result = provider.recommend(actor(), request(constraints={'formats': ['course']}))
    assert len(result.items) == 1
    assert result.items[0].access_type == 'По подписке'
    assert result.items[0].requires_access_check is True
    assert result.items[0].listed_price is None


def test_out_of_domain_and_empty_eligible_are_persisted_honestly(serving):
    provider, _ = serving
    a = actor()
    out = provider.recommend(a, request(task='кваркглюонная гравитация'))
    assert out.status == 'needs_clarification' and not out.items and out.message
    empty = provider.recommend(a, request(constraints={'formats': ['podcast']}))
    assert empty.status == 'no_eligible' and not empty.items and empty.message


def test_parallel_retries_are_atomic_and_return_same_response(serving):
    provider, sessions = serving
    a, q = actor(), request()
    with ThreadPoolExecutor(max_workers=6) as pool:
        outputs = list(pool.map(lambda _: provider.recommend(a, q), range(6)))
    assert all(out == outputs[0] for out in outputs)
    with sessions() as db:
        assert count(db, Decision) == count(db, ServingRequest) == 1


def test_failure_after_decision_rolls_back_everything(serving, monkeypatch):
    import app.services.ml_recommendation_provider as module
    provider, sessions = serving
    def broken(**kwargs):
        raise ValueError('simulated mapping failure')
    monkeypatch.setattr(module, 'RecommendationCard', broken)
    with pytest.raises(ProviderUnavailable):
        provider.recommend(actor(), request())
    with sessions() as db:
        assert count(db, Decision) == count(db, DecisionItem) == count(db, ServingRequest) == 0


def test_restart_and_model_update_keep_the_original_receipt(serving, monkeypatch):
    provider, sessions = serving
    a, q = actor(), request()
    original = provider.recommend(a, q)
    old_model_id = provider._model_cache.state_id
    events = EventService(sessions)
    item = original.items[0]
    impression = events.acknowledge(a, VisibilityAck(event_key=uuid4(), item_id=item.item_id,
        material_key=item.material_key, visible_ms=1200, visible_fraction=.8))
    events.action(a, ClientAction(event_key=uuid4(), item_id=item.item_id,
        material_key=item.material_key, impression_id=impression['id'], kind='click'))
    assert LearningService(sessions).tick(datetime.now(timezone.utc) + timedelta(days=2)) == 1
    provider.recommend(a, request())
    assert provider._model_cache.state_id != old_model_id
    assert provider.recommend(a, q) == original
    restarted = MLRecommendationProvider(provider.index, provider.manifest, provider.materials,
                                         provider.engine, provider.secret)
    def never_recalculate(*args, **kwargs):
        raise AssertionError('a saved retry must not repeat retrieval')
    monkeypatch.setattr(restarted.search, 'query', never_recalculate)
    assert restarted.recommend(a, q) == original


def test_unavailable_model_falls_back_to_prior_without_fake_scores(serving, monkeypatch):
    provider, _ = serving
    def missing(_db):
        raise ValueError('incompatible model')
    monkeypatch.setattr(provider, '_model', missing)
    result = provider.recommend(actor(), request())
    assert result.items and result.message == 'Временно использовано базовое ранжирование.'
    assert 'score' not in result.model_dump(mode='json')['items'][0]


def test_mismatched_catalog_and_index_fail_closed(tmp_path, monkeypatch):
    import json
    import app.services.ml_recommendation_provider as module
    (tmp_path / 'manifest.json').write_text(json.dumps({'files': {'materials.jsonl': 'different'}}))
    monkeypatch.setattr(module, 'verify_index', lambda *_: ({'bundle_id': 'index'}, {}))
    monkeypatch.setattr(module, 'load_ranking_catalog', lambda *_: (object(),
        {'bundle_id': 'index', 'catalog_files': {'materials.jsonl': 'expected'}, 'catalog_bundle_id': 'x'}, []))
    config = SimpleNamespace(session_secret='x' * 32, catalog_dir=str(tmp_path), retrieval_index_dir=str(tmp_path))
    with pytest.raises(ValueError, match='checksums'):
        MLRecommendationProvider.load(config)


def test_unavailable_catalog_keeps_api_unavailable(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.core.config import get_settings
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@127.0.0.1/alfakurs')
    monkeypatch.setenv('ALFA_RECOMMENDATIONS_ENABLED', 'true')
    monkeypatch.setenv('ALFA_CATALOG_DIR', str(tmp_path / 'missing'))
    monkeypatch.setenv('ALFA_RETRIEVAL_INDEX_DIR', str(tmp_path / 'missing-index'))
    monkeypatch.setenv('ALFA_SESSION_SECRET', 'x' * 32)
    monkeypatch.setenv('ALFA_SESSION_COOKIE_SECURE', 'false')
    get_settings.cache_clear()
    from app.main import create_app
    with TestClient(create_app()) as client:
        session = client.post('/api/v1/session')
        response = client.post('/api/v1/recommendations', headers={'X-CSRF-Token': session.json()['csrf_token']},
                               json={'request_key': str(uuid4()), 'task': 'НДС'})
        assert response.status_code == 503
        assert 'decision_id' not in response.json()
    get_settings.cache_clear()


def test_corrupted_index_verification_fails_before_loading(tmp_path, monkeypatch):
    import app.services.ml_recommendation_provider as module
    def corrupted(*_):
        raise ValueError('Checksum mismatch: matrix.npz')
    monkeypatch.setattr(module, 'verify_index', corrupted)
    config = SimpleNamespace(session_secret='x' * 32, catalog_dir=str(tmp_path), retrieval_index_dir=str(tmp_path))
    with pytest.raises(ValueError, match='Checksum mismatch'):
        MLRecommendationProvider.load(config)
