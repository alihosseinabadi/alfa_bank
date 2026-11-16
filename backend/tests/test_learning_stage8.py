from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import numpy as np
from sqlalchemy import select
from app.models.learning import RewardObservation, RewardRevision
from app.services.learning_service import LearningService
from app.ml.reward_policy import RewardPolicy
from test_event_storage_stage7 import store, issue, ack, action

def test_zero_late_click_retry_and_replay(store):
    service, sessions, _ = store
    actor, _, _, _, _, item, _ = issue(service, simulated=False)
    service.acknowledge(actor, ack(item))
    worker = LearningService(sessions, policy=RewardPolicy(maturity_seconds=1, attribution_seconds=604800))
    now = datetime.now(timezone.utc) + timedelta(seconds=2)
    assert worker.tick(now) == 1
    zero = worker.replay()
    service.action(actor, action(item))
    assert worker.tick(now) == 1
    assert worker.tick(now) == 0
    updated = worker.replay()
    np.testing.assert_array_equal(zero.A, updated.A)
    assert np.linalg.norm(updated.b) > 0
    with sessions() as db:
        obs = db.scalars(select(RewardObservation)).one()
        assert obs.reward == .1 and obs.revision == 2
        assert len(db.scalars(select(RewardRevision)).all()) == 2

def test_simulated_and_concurrent_ticks(store):
    service, sessions, _ = store
    actor, _, _, _, _, item, _ = issue(service, simulated=True)
    service.acknowledge(actor, ack(item))
    actor2, _, _, _, _, item2, _ = issue(service, simulated=False)
    service.acknowledge(actor2, ack(item2))
    worker = LearningService(sessions, policy=RewardPolicy(maturity_seconds=1, attribution_seconds=100))
    now = datetime.now(timezone.utc) + timedelta(seconds=2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: worker.tick(now), range(2))) == [0, 1]
    with sessions() as db:
        assert len(db.scalars(select(RewardObservation)).all()) == 1

def test_incompatible_configuration_and_backward_clock(store):
    import pytest
    service, sessions, _ = store
    actor, _, _, _, _, item, _ = issue(service, simulated=False)
    service.acknowledge(actor, ack(item))
    policy = RewardPolicy(maturity_seconds=1, attribution_seconds=100)
    worker = LearningService(sessions, policy=policy)
    now = datetime.now(timezone.utc) + timedelta(seconds=3)
    assert worker.tick(now) == 1
    with pytest.raises(ValueError, match='clock'):
        worker.tick(now - timedelta(seconds=1))
    with pytest.raises(ValueError, match='incompatible'):
        LearningService(sessions, policy=policy, ridge=2).replay()
    with sessions() as db:
        assert len(db.scalars(select(RewardRevision)).all()) == 1

def test_ucb_ranking_and_checkpoint(store, tmp_path):
    from app.services.learning_checkpoint import write_checkpoint, load_checkpoint
    from app.ml.ucb_ranking import rank_ucb
    from test_event_storage_stage7 import issue
    service, sessions, _ = store
    a, context, prior, key, decision, item, batch = issue(service, simulated=False)
    worker = LearningService(sessions)
    path = tmp_path / 'checkpoint.json'
    state_id = write_checkpoint(path, worker)
    model = load_checkpoint(path, worker)
    result = rank_ucb(prior, model, state_id)
    assert result.candidates[0].ucb_score == result.candidates[0].exploit + result.candidates[0].explore
    from uuid import uuid4
    response = service.issue(a, uuid4(), result, context, retrieval_batch=batch)
    from app.models.events import DecisionItem
    from uuid import UUID
    with sessions() as db:
        saved = db.get(DecisionItem, UUID(response['items'][0]['item_id']))
        assert saved.snapshot['ucb']['score'] == result.candidates[0].ucb_score
    import pytest
    path.write_text(path.read_text().replace('linucb-checkpoint-v1','broken'))
    with pytest.raises(ValueError): load_checkpoint(path, worker)

def test_worker_transaction_rolls_back(store, monkeypatch):
    import pytest
    from app.models.learning import RewardRevision
    service, sessions, _ = store
    actor, _, _, _, _, item, _ = issue(service, simulated=False)
    service.acknowledge(actor, ack(item))
    worker = LearningService(sessions, policy=RewardPolicy(maturity_seconds=1, attribution_seconds=100))
    original = RewardRevision.__init__
    def fail(*args, **kwargs): raise RuntimeError('injected failure')
    monkeypatch.setattr(RewardRevision, '__init__', fail)
    now = datetime.now(timezone.utc) + timedelta(seconds=3)
    with pytest.raises(RuntimeError): worker.tick(now)
    with sessions() as db: assert not db.scalars(select(RewardObservation)).all()
    monkeypatch.setattr(RewardRevision, '__init__', original)
    assert worker.tick(now) == 1

def test_parameter_change_rejects_stale_state(store):
    import pytest
    from app.ml.ucb_ranking import rank_ucb
    service, sessions, _ = store
    _, _, prior, _, _, _, _ = issue(service, simulated=False)
    model = LearningService(sessions).replay()
    state = model.state_id
    model.alpha += 1
    with pytest.raises(ValueError, match='changed'):
        rank_ucb(prior, model, state)

def test_failed_model_falls_back_to_prior(store):
    from app.ml.ucb_ranking import rank_with_fallback
    service, _, _ = store
    _, _, prior, _, _, _, _ = issue(service, simulated=False)
    def fail(): raise ValueError('invalid checkpoint')
    result, reason = rank_with_fallback(prior, fail)
    assert result is prior and reason == 'ValueError'

def test_malformed_checkpoint_falls_back(store, tmp_path):
    from app.ml.ucb_ranking import rank_with_fallback
    from app.services.learning_checkpoint import load_checkpoint
    service, sessions, _ = store
    _, _, prior, _, _, _, _ = issue(service, simulated=False)
    path = tmp_path / 'invalid.json'
    path.write_text('{}')
    result, reason = rank_with_fallback(prior, lambda: load_checkpoint(path, LearningService(sessions)))
    assert result is prior and reason == 'KeyError'

def test_checkpoint_rejects_changed_model_parameters(store, tmp_path):
    import hashlib, json, pytest
    from app.services.learning_checkpoint import write_checkpoint, load_checkpoint, canonical
    _, sessions, _ = store
    worker = LearningService(sessions)
    path = tmp_path / 'model.json'
    write_checkpoint(path, worker)
    envelope = json.loads(path.read_text())
    envelope['body']['alpha'] = 10
    envelope['sha256'] = hashlib.sha256(canonical(envelope['body'])).hexdigest()
    path.write_bytes(canonical(envelope))
    with pytest.raises(ValueError): load_checkpoint(path, worker)

def test_unavailable_database_falls_back(store):
    from sqlalchemy.exc import OperationalError
    from app.services.learning_ranking import rank_with_learning_service
    service, _, _ = store
    _, _, prior, _, _, _, _ = issue(service, simulated=False)
    def fail(): raise OperationalError('query', {}, Exception('unavailable'))
    result, reason = rank_with_learning_service(prior, fail)
    assert result is prior and reason == 'database_unavailable'

def test_late_payment_only_one_impression_and_repeat(store):
    import pytest
    from uuid import uuid4
    from app.schemas.events import PaymentPrincipal
    from app.services.event_service import EventService, EventConflict
    from test_event_storage_stage7 import purchase
    service, sessions, _ = store
    actor, _, _, _, _, one, _ = issue(service, simulated=False, access='По подписке')
    _, _, _, _, _, two, _ = issue(service, a=actor, simulated=False, access='По подписке')
    service.acknowledge(actor, ack(one)); service.acknowledge(actor, ack(two))
    policy = RewardPolicy(maturity_seconds=1, attribution_seconds=604800, allow_verified_payments=True)
    worker = LearningService(sessions, policy=policy)
    now = datetime.now(timezone.utc) + timedelta(seconds=5)
    assert worker.tick(now) == 2
    before = worker.replay()
    # Synthetic test of the trusted boundary: production adapter is not implemented.
    test_gateway = EventService(sessions, allow_live_payments=True)
    request = purchase(one, occurred_at=datetime.now(timezone.utc))
    principal = PaymentPrincipal(provider='synthetic_gateway', environment='production')
    payment = test_gateway.purchase(actor, request, principal)
    assert test_gateway.purchase(actor, request, principal)['id'] == payment['id']
    with pytest.raises(EventConflict):
        test_gateway.purchase(actor, purchase(two, transaction_key=request.transaction_key, occurred_at=request.occurred_at), principal)
    assert worker.tick(now + timedelta(seconds=1)) == 1
    assert worker.tick(now + timedelta(seconds=2)) == 0
    after = worker.replay()
    np.testing.assert_array_equal(before.A, after.A)
    with sessions() as db:
        assert sorted(x.reward for x in db.scalars(select(RewardObservation)).all()) == [0,1]

def test_order_of_late_click_and_open_converges(store):
    service, sessions, _ = store
    actor, _, _, _, _, item, _ = issue(service, simulated=False)
    service.acknowledge(actor, ack(item))
    policy = RewardPolicy(maturity_seconds=1, attribution_seconds=100)
    a = LearningService(sessions, model_key='order-a', policy=policy)
    b = LearningService(sessions, model_key='order-b', policy=policy)
    now = datetime.now(timezone.utc) + timedelta(seconds=5)
    a.tick(now); b.tick(now)
    service.action(actor, action(item, kind='click'))
    a.tick(now+timedelta(seconds=1))
    service.action(actor, action(item, kind='material_open'))
    a.tick(now+timedelta(seconds=2)); b.tick(now+timedelta(seconds=2))
    x, y = a.replay(), b.replay()
    np.testing.assert_array_equal(x.A,y.A)
    np.testing.assert_array_equal(x.b,y.b)
    with sessions() as db:
        assert all(o.reward == .15 for o in db.scalars(select(RewardObservation)).all())

def test_replay_in_fresh_process(store):
    import os, subprocess, sys, json
    from pathlib import Path
    from sqlalchemy import text
    service, sessions, engine = store
    actor, _, _, _, _, item, _ = issue(service, simulated=False)
    service.acknowledge(actor, ack(item))
    worker = LearningService(sessions)
    worker.tick(datetime.now(timezone.utc) + timedelta(days=2))
    expected = worker.replay().state_id
    with engine.connect() as db: schema = db.scalar(text('SHOW search_path'))
    env = os.environ.copy()
    env['ALFA_EVENTS_DATABASE_URL'] = engine.url.render_as_string(hide_password=False)
    env['PGOPTIONS'] = '-csearch_path=' + schema
    root = Path(__file__).resolve().parents[2]
    env['PYTHONPATH'] = str(root / 'backend')
    code = 'from app.database.connection import events_engine,events_sessions; from app.services.learning_service import LearningService; print(LearningService(events_sessions(events_engine())).replay().state_id)'
    actual = subprocess.check_output([sys.executable,'-c',code],cwd=root,env=env,text=True).strip()
    assert actual == expected
