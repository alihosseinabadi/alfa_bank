from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from uuid import uuid4
from app.ml.reward_policy import RewardPolicy

def test_maturity_and_late_positive_and_trust():
    now = datetime.now(timezone.utc)
    i = NS(id=uuid4(), item_id=uuid4(), confirmed_at=now)
    e = NS(simulated=False, impression_id=i.id, item_id=i.item_id, ingested_at=now+timedelta(seconds=1), kind='click', source='client', trust='client_reported')
    p = RewardPolicy(maturity_seconds=10, attribution_seconds=100)
    assert p.reward(i, [], now+timedelta(seconds=9)) is None
    assert p.reward(i, [], now+timedelta(seconds=11)) == 0
    assert p.reward(i, [e,e], now+timedelta(seconds=11)) == 0.1
    e.simulated = True
    assert p.reward(i, [e], now+timedelta(seconds=11)) == 0

def test_payment_is_disabled_and_future_payment_not_attributed():
    now = datetime.now(timezone.utc)
    i = NS(id=uuid4(), item_id=uuid4(), confirmed_at=now-timedelta(seconds=10))
    e = NS(simulated=False, impression_id=i.id, item_id=i.item_id, ingested_at=now, kind='purchase_confirmed', source='payment_server', trust='server_verified', payment_environment='production', client_time=now+timedelta(seconds=1))
    policy = RewardPolicy(maturity_seconds=1, attribution_seconds=100)
    assert policy.reward(i,[e],now) == 0
    enabled = RewardPolicy(maturity_seconds=1, attribution_seconds=100, allow_verified_payments=True)
    assert enabled.reward(i,[e],now) == 0
    e.client_time = now-timedelta(seconds=1)
    assert enabled.reward(i,[e],now) == 1
    e.simulated = True
    assert enabled.reward(i,[e],now) == 0

def test_late_event_order_is_commutative():
    from itertools import permutations
    now = datetime.now(timezone.utc)
    i = NS(id=uuid4(), item_id=uuid4(), confirmed_at=now-timedelta(seconds=5))
    common = dict(simulated=False, impression_id=i.id, item_id=i.item_id, ingested_at=now, source='client', trust='client_reported')
    events = [NS(**common,kind='click',is_free_open=False), NS(**common,kind='material_open',is_free_open=True)]
    p = RewardPolicy(maturity_seconds=1, attribution_seconds=100)
    assert [p.reward(i,list(order),now) for order in permutations(events)] == [.15,.15]
