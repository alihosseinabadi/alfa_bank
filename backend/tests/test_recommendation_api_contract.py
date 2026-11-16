"""HTTP boundary tests; the injected provider is explicitly synthetic."""
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.anonymous_session import InvalidSession, read_cookie
from app.core.config import get_settings
from app.schemas.recommendation import RecommendationResponse
from app.services.recommendation_provider import RequestConflict

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT / 'tests/fixtures/recommendation-api-response.json').read_text(encoding='utf-8'))


class FakeProvider:
    """Test double only: real persistence/idempotency is not implemented here."""
    def __init__(self):
        self.saved = {}
        self.calls = 0

    def recommend(self, actor, request):
        self.calls += 1
        key = (actor.actor_id, request.request_key)
        value = request.model_dump_json()
        if key in self.saved and self.saved[key] != value:
            raise RequestConflict()
        self.saved[key] = value
        return FIXTURE


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ALFA_SESSION_SECRET', 'test-secret-' + 'x' * 32)
    monkeypatch.setenv('ALFA_SESSION_COOKIE_SECURE', 'false')
    monkeypatch.setenv('API_CORS_ORIGINS', 'http://localhost:5173')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1/contract_test')
    get_settings.cache_clear()
    from app.main import create_app
    app = create_app()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def start_session(client):
    response = client.post('/api/v1/session')
    assert response.status_code == 200
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert response.headers['cache-control'] == 'no-store'
    return {'X-CSRF-Token': response.json()['csrf_token']}


def body(**kwargs):
    return {'request_key': str(uuid4()), 'task': 'Хочу найти клиентов', **kwargs}


def test_no_session_csrf_and_unconfigured_provider(client):
    assert client.post('/api/v1/recommendations', json=body()).status_code == 401
    headers = start_session(client)
    assert client.post('/api/v1/recommendations', json=body()).status_code == 403
    response = client.post('/api/v1/recommendations', headers=headers, json=body())
    assert response.status_code == 503
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == {'detail': 'Recommendation service is not configured'}


def test_synthetic_provider_contract_retry_conflict_and_actor_isolation(client):
    fake = FakeProvider()
    client.app.state.recommendation_provider = fake
    headers = start_session(client)
    request = body(profile={'business_stage': 'Запускаю бизнес', 'industry': 'Торговля'},
                   constraints={'formats': ['article'], 'budget_preference': 'paid_allowed', 'available_time_minutes': 30})
    first = client.post('/api/v1/recommendations', headers=headers, json=request)
    assert first.status_code == 200, first.text
    assert first.json() == FIXTURE
    assert client.post('/api/v1/recommendations', headers=headers, json=request).json() == first.json()
    assert client.post('/api/v1/recommendations', headers=headers, json={**request, 'task': 'Другая задача'}).status_code == 409
    # A second server-issued session cannot claim the first anonymous actor.
    with TestClient(client.app) as other:
        other_headers = start_session(other)
        assert other.post('/api/v1/recommendations', headers=other_headers, json={**request, 'task': 'Другая задача'}).status_code == 200
    assert len(fake.saved) == 2


def test_validation_and_untrusted_user_identity(client):
    fake = FakeProvider(); client.app.state.recommendation_provider = fake
    headers = start_session(client)
    assert client.post('/api/v1/recommendations', headers=headers, json=body(user_id=123)).status_code == 401
    for bad in [body(task=' '), body(task='x' * 301), body(request_key='not-a-uuid'),
                body(constraints={'formats': ['bad']}), body(constraints={'formats': ['course', 'course']}),
                body(constraints={'available_time_minutes': 0}), body(limit=7), body(seed=5)]:
        assert client.post('/api/v1/recommendations', headers=headers, json=bad).status_code == 422
    private_input = 'личное-' + 'x' * 301
    rejected = client.post('/api/v1/recommendations', headers=headers, json=body(task=private_input))
    assert rejected.status_code == 422 and private_input not in rejected.text
    assert 'input' not in rejected.json()['detail'][0]
    assert fake.calls == 0
    # The public boundary also rejects a provider that violates explicit filters.
    assert client.post('/api/v1/recommendations', headers=headers, json=body(constraints={'budget_preference': 'free_only'})).status_code == 502
    assert client.post('/api/v1/recommendations', headers=headers, json=body(constraints={'formats': ['course']})).status_code == 502
    assert client.post('/api/v1/recommendations', headers=headers, json=body(constraints={'available_time_minutes': 5})).status_code == 502


def test_tampered_session_bad_csrf_and_recovery(client):
    headers = start_session(client)
    cookie = client.cookies.get('alfa_anon_session')
    client.cookies.set('alfa_anon_session', cookie[:-1] + ('0' if cookie[-1] != '0' else '1'), domain='testserver.local', path='/')
    assert client.post('/api/v1/recommendations', headers=headers, json=body()).status_code == 401
    # Session endpoint replaces a corrupted cookie with a fresh, server-issued identity.
    new = client.post('/api/v1/session')
    assert new.status_code == 200 and 'set-cookie' in new.headers
    assert client.post('/api/v1/recommendations', headers=headers, json=body()).status_code == 403
    with pytest.raises(InvalidSession):
        read_cookie('x' * 32, 'v1.' + uuid4().hex + '.9999999999.' + 'я' * 64)


def test_cors_is_explicit_and_credentialed(client):
    headers = {'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST',
               'Access-Control-Request-Headers': 'content-type,x-csrf-token'}
    ok = client.options('/api/v1/recommendations', headers=headers)
    assert ok.status_code == 200
    assert ok.headers['access-control-allow-origin'] == 'http://localhost:5173'
    assert ok.headers['access-control-allow-credentials'] == 'true'
    denied = client.options('/api/v1/recommendations', headers={**headers, 'Origin': 'https://attacker.example'})
    assert denied.status_code == 400 and 'access-control-allow-origin' not in denied.headers


def test_public_response_rejects_private_fields_and_inconsistent_items(client):
    class Leaky:
        def recommend(self, actor, request):
            return {**FIXTURE, 'seed': 42}
    client.app.state.recommendation_provider = Leaky()
    assert client.post('/api/v1/recommendations', headers=start_session(client), json=body()).status_code == 502
    for invalid in [
        {**FIXTURE, 'status': 'no_eligible'},
        {**FIXTURE, 'items': [{**FIXTURE['items'][0], 'position': 2}]},
        {**FIXTURE, 'items': [{**FIXTURE['items'][0], 'url': 'javascript:alert(1)'}]},
        {**FIXTURE, 'items': [{**FIXTURE['items'][0], 'requires_access_check': False}]},
    ]:
        with pytest.raises(ValueError):
            RecommendationResponse.model_validate(invalid)


def test_empty_status_needs_message():
    for status in ('no_eligible', 'needs_clarification'):
        valid = {'status': status, 'decision_id': str(uuid4()), 'items': [], 'message': 'Уточните задачу'}
        assert RecommendationResponse.model_validate(valid).items == []
        with pytest.raises(ValueError):
            RecommendationResponse.model_validate({**valid, 'message': None})
