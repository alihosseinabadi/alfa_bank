"""Integration boundaries between the legacy HTTP app and ML event storage."""
import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

ROOT = Path(__file__).resolve().parents[2]


def test_event_and_product_models_use_separate_metadata():
    from app.database.base import Base, ProductBase
    import app.models.events
    import app.models.learning
    assert Base.metadata is not ProductBase.metadata
    event = Base.metadata.tables['recommendation_impressions']
    product = ProductBase.metadata.tables['recommendation_impressions']
    assert 'item_id' in event.c and 'user_id' not in event.c
    assert 'user_id' in product.c and 'item_id' not in product.c


def test_ml_imports_do_not_require_product_configuration():
    env = os.environ.copy()
    env.pop('DATABASE_URL', None)
    env.pop('ALFA_EVENTS_DATABASE_URL', None)
    env['PYTHONPATH'] = str(ROOT / 'backend')
    result = subprocess.run(
        [sys.executable, '-c', 'from app.services.event_service import EventService; from app.services.learning_service import LearningService'],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_product_database_cannot_be_events_database(monkeypatch):
    from app.core.config import get_settings
    from app.database.connection import product_engine
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://x:x@127.0.0.1/alfa_events_test')
    get_settings.cache_clear()
    product_engine.cache_clear()
    try:
        with pytest.raises(ValueError, match='must not target'):
            product_engine()
    finally:
        get_settings.cache_clear()
        product_engine.cache_clear()


def test_connection_rejects_database_alias_to_different_physical_db():
    from unittest.mock import MagicMock
    from app.database.connection import _checked_engine

    dbapi = MagicMock()
    cursor = dbapi.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = ('alfa_events_test',)
    # Exercise the actual connect listener without requiring a proxy to alias DB names.
    engine = _checked_engine('postgresql+psycopg://x:x@localhost/alfa_product_test')
    listener = list(engine.pool.dispatch.connect)[-1]
    with pytest.raises(ValueError, match='unexpected PostgreSQL database'):
        listener(dbapi, None)
    cursor.execute.assert_called_once_with('SELECT current_database()')
    dbapi.rollback.assert_called_once()
    engine.dispose()


def test_product_api_and_migration_against_isolated_postgresql(monkeypatch):
    url = os.environ.get('ALFA_PRODUCT_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set ALFA_PRODUCT_TEST_DATABASE_URL to an isolated alfa_product_test database')
    if make_url(url).database != 'alfa_product_test':
        raise ValueError('Tests require a dedicated alfa_product_test database')
    monkeypatch.setenv('DATABASE_URL', url)
    from app.core.config import get_settings
    from app.database.connection import get_db, product_engine
    get_settings.cache_clear()
    product_engine.cache_clear()
    from app.main import create_app
    from fastapi.testclient import TestClient

    admin = create_engine(url)
    schema = 'stage2_test_' + uuid4().hex
    assert re.fullmatch(r'stage2_test_[a-f0-9]{32}', schema)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    test_engine = create_engine(url, connect_args={'options': '-csearch_path=' + schema})
    try:
        config = Config(str(ROOT / 'backend/product-alembic.ini'))
        with test_engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        sessions = sessionmaker(bind=test_engine)
        def override_db():
            with sessions() as db:
                yield db
        app = create_app()
        app.dependency_overrides[get_db] = override_db
        with TestClient(app) as client:
            email = 'stage2@example.com'
            response = client.post('/api/v1/users/', json={'email': email, 'experience': 'Есть опыт'})
            assert response.status_code == 201, response.text
            assert response.json()['experience'] == 'Есть опыт'
            assert response.json()['current_goal'] is None
            assert client.get('/api/v1/users/' + str(response.json()['id'])).json()['email'] == email
            assert client.post('/api/v1/users/', json={'email': email}).status_code == 409
            course = {'title': 'Пробный материал', 'description': 'Тест', 'type': 'article',
                      'price': '0', 'is_free': True, 'duration_minutes': 5,
                      'category': 'Тест', 'difficulty': 'базовый', 'source': 'synthetic'}
            assert client.post('/api/v1/courses/', json=course).status_code == 201
            assert len(client.get('/api/v1/courses/').json()) == 1
            assert client.get('/api/v1/recommendations/1').status_code == 503
            assert client.post('/api/v1/interactions/', json={'impression_id': 1, 'event_type': 'purchase'}).status_code == 503
    finally:
        test_engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()
