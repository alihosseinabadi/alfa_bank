"""Real PostgreSQL integration gates; no organizer DB or SQLite substitute."""
import json,os,re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from uuid import UUID,uuid4
import pytest
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select,func
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema,DropSchema
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.database.connection import events_engine,events_sessions
from app.database.base import Base
from app.models.events import Actor,Decision,DecisionItem,Impression,Interaction,MessageReceipt
from app.schemas.events import TrustedActor,VisibilityAck,ClientAction,PaymentNotice,PaymentPrincipal
from app.services.event_service import EventService,EventConflict,ItemNotFound,VisibilityRequired,InvalidEventTime
from test_prior_ranking_stage6 import setup,material
from app.ml.prior_ranking import rank_candidates

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def store():
    url=os.environ.get("ALFA_EVENTS_TEST_DATABASE_URL")
    if not url:pytest.skip("Set ALFA_EVENTS_TEST_DATABASE_URL for real PostgreSQL gates")
    if make_url(url).database!="alfa_events_test":raise ValueError("Tests require isolated alfa_events_test DB")
    admin=events_engine(url)
    schema="stage7_test_"+uuid4().hex
    assert re.fullmatch("stage7_test_[a-f0-9]{32}",schema)
    with admin.begin() as c:c.execute(CreateSchema(schema))
    engine=events_engine(url,connect_args={"options":"-csearch_path="+schema})
    try:
        config=Config(str(ROOT/"backend/alembic.ini"))
        with engine.begin() as c:
            config.attributes["connection"]=c
            command.upgrade(config,"head")
        sessions=events_sessions(engine)
        yield EventService(sessions),sessions,engine
    finally:
        engine.dispose()
        # Only the unique schema created by this fixture in the explicit test DB.
        assert re.fullmatch("stage7_test_[a-f0-9]{32}",schema)
        with admin.begin() as c:c.execute(DropSchema(schema,cascade=True))
        admin.dispose()

def actor(kind="anonymous"):
    return TrustedActor(actor_id=uuid4(),session_id=uuid4(),kind=kind)

def issue(service,a=None,*,access="Открытый",simulated=True):
    a=a or actor()
    p,c,m,b=setup(materials=[material(access_type=access,listed_price=0)])
    r=rank_candidates(b,m,c,profile=p)
    key=uuid4();decision=service.issue(a,key,r,c,retrieval_batch=b,simulated=simulated)
    return a,c,r,key,decision,decision["items"][0],b

def ack(item,**changes):
    return VisibilityAck(**dict(dict(event_key=uuid4(),item_id=item["item_id"],material_key=item["material_key"],
                                    visible_ms=1200,visible_fraction=.8),**changes))

def action(item,**changes):
    return ClientAction(**dict(dict(event_key=uuid4(),item_id=item["item_id"],material_key=item["material_key"],kind="click"),**changes))

def purchase(item,**changes):
    return PaymentNotice(**dict(dict(event_key=uuid4(),item_id=item["item_id"],material_key=item["material_key"],
        transaction_key="test-"+uuid4().hex,amount=Decimal("100.00"),currency="RUB"),**changes))

def counts(sessions):
    with sessions() as db:return {t.__tablename__:db.scalar(select(func.count()).select_from(t))
                                 for t in (Actor,Decision,DecisionItem,Impression,Interaction,MessageReceipt)}

def test_decision_is_not_an_impression_and_features_are_frozen(store):
    service,sessions,_=store
    a,c,r,key,d,item,b=issue(service)
    original=r.candidates[0].features.model_dump(mode="json")
    r.candidates[0].features.vector[1]=.123
    with sessions() as db:
        stored=db.get(DecisionItem,UUID(item["item_id"]))
        assert stored.snapshot["features"]==original
        assert stored.snapshot["retrieval_score"]==b.hits[0].raw_score
        metadata=db.get(Decision,UUID(d["decision_id"])).snapshot
        assert metadata["selection_mode"]=="deterministic" and metadata["action_probability"] is None
        assert metadata["context"]["history_weight"]==c.history_weight
        assert "query_text" not in metadata["context"] and "user_key" not in metadata["context"]
    assert counts(sessions)["recommendation_impressions"]==0

def test_issue_retry_and_conflict(store):
    service,sessions,_=store
    a,c,r,key,d,item,b=issue(service)
    assert service.issue(a,key,r,c,retrieval_batch=b,simulated=True)["decision_id"]==d["decision_id"]
    with pytest.raises(EventConflict):service.issue(a,key,r,c,retrieval_batch=b,simulated=False)
    assert counts(sessions)["recommendation_decisions"]==1

def test_action_before_visibility_rejects_without_event_then_retry_succeeds(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    request=action(item)
    with pytest.raises(VisibilityRequired):service.action(a,request)
    assert counts(sessions)["interaction_events"]==counts(sessions)["event_receipts"]==0
    service.acknowledge(a,ack(item))
    first=service.action(a,request)
    assert service.action(a,request)["id"]==first["id"]
    assert service.action(a,request)["impression_id"]==first["impression_id"]
    assert counts(sessions)["interaction_events"]==1

def test_visibility_keys_and_canonical_impression(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    request=ack(item);first=service.acknowledge(a,request)
    assert service.acknowledge(a,request)["id"]==first["id"]
    assert service.acknowledge(a,ack(item))["id"]==first["id"]
    with pytest.raises(EventConflict):service.acknowledge(a,request.model_copy(update={"visible_ms":3000}))
    assert counts(sessions)["recommendation_impressions"]==1
    assert counts(sessions)["event_receipts"]==2

def test_generic_message_key_cannot_change_kind(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    visibility=ack(item);service.acknowledge(a,visibility)
    with pytest.raises(EventConflict):service.action(a,action(item,event_key=visibility.event_key))
    assert counts(sessions)["interaction_events"]==0

def test_wrong_actor_material_and_impression_rejected(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    with pytest.raises(ItemNotFound):service.acknowledge(actor(),ack(item))
    with pytest.raises(ItemNotFound):service.acknowledge(a,ack(item,material_key="other"))
    service.acknowledge(a,ack(item))
    with pytest.raises(ItemNotFound):service.action(a,action(item,impression_id=uuid4()))
    assert counts(sessions)["interaction_events"]==0

def test_anonymous_session_binding_and_authenticated_session_change(store):
    service,_,_=store
    a,_,_,_,_,item,_=issue(service)
    with pytest.raises(EventConflict):
        service.acknowledge(a.model_copy(update={"session_id":uuid4()}),ack(item))
    auth,_,_,_,_,auth_item,_=issue(service,actor("authenticated"))
    assert service.acknowledge(auth.model_copy(update={"session_id":uuid4()}),ack(auth_item))["id"]

@pytest.mark.parametrize("days",[8,-1])
def test_client_time_range_rolls_back(store,days):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    with pytest.raises(InvalidEventTime):
        service.acknowledge(a,ack(item,client_time=datetime.now(timezone.utc)-timedelta(days=days)))
    assert counts(sessions)["recommendation_impressions"]==0

def test_same_instant_timezone_is_same_idempotent_message(store):
    service,_,_=store
    a,_,_,_,_,item,_=issue(service)
    stamp=datetime.now(timezone.utc)
    request=ack(item,client_time=stamp)
    first=service.acknowledge(a,request)
    assert service.acknowledge(a,request.model_copy(update={"client_time":stamp.astimezone(timezone(timedelta(hours=3)))}))["id"]==first["id"]

@pytest.mark.parametrize("access,expected",[("Открытый",True),("По подписке",False)])
def test_free_open_uses_access_not_zero_price(store,access,expected):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service,access=access)
    service.acknowledge(a,ack(item))
    output=service.action(a,action(item,kind="material_open"))
    with sessions() as db:
        event=db.get(Interaction,UUID(output["id"]))
        assert event.is_free_open is expected
        assert not event.qualified_use and event.trust=="client_reported"

def test_client_cannot_assert_payment_or_actor_or_reward():
    base=dict(event_key=uuid4(),item_id=uuid4(),material_key="course:test")
    for changes in ({"kind":"purchase_confirmed"},{"kind":"click","actor_id":str(uuid4())},{"kind":"click","reward":10}):
        with pytest.raises(ValidationError):ClientAction(**base,**changes)
    with pytest.raises(ValidationError):
        VisibilityAck(**base,visible_ms=10,visible_fraction=.8)

def test_verified_test_payment_is_unique_by_transaction_even_with_new_event_key(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service,access="По подписке")
    service.acknowledge(a,ack(item))
    request=purchase(item);principal=PaymentPrincipal(provider="test_gateway")
    first=service.purchase(a,request,principal)
    assert service.purchase(a,request,principal)["id"]==first["id"]
    assert service.purchase(a,request.model_copy(update={"event_key":uuid4(),"amount":Decimal("100.0")}),principal)["id"]==first["id"]
    with pytest.raises(EventConflict):
        service.purchase(a,request.model_copy(update={"event_key":uuid4(),"amount":Decimal("101")}),principal)
    with sessions() as db:
        stored=db.get(Interaction,UUID(first["id"]))
        assert stored.simulated and stored.trust=="server_verified"
    assert counts(sessions)["interaction_events"]==1

def test_live_payments_disabled_and_transaction_cannot_move_to_another_actor(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service);service.acknowledge(a,ack(item))
    request=purchase(item)
    with pytest.raises(EventConflict):service.purchase(a,request,PaymentPrincipal(provider="gateway",environment="production"))
    service.purchase(a,request,PaymentPrincipal(provider="gateway"))
    b,_,_,_,_,other,_=issue(service);service.acknowledge(b,ack(other))
    with pytest.raises(EventConflict):
        service.purchase(b,purchase(other,transaction_key=request.transaction_key),PaymentPrincipal(provider="gateway"))
    assert counts(sessions)["interaction_events"]==1

def test_partial_slate_failure_rolls_back_every_row(store,monkeypatch):
    service,sessions,_=store
    p,c,m,b=setup();r=rank_candidates(b,m,c,profile=p)
    original=service._insert_items
    def fail(db,decision,items):
        original(db,decision,items)
        raise RuntimeError("simulated crash before commit")
    monkeypatch.setattr(service,"_insert_items",fail)
    with pytest.raises(RuntimeError):service.issue(actor(),uuid4(),r,c,retrieval_batch=b,simulated=True)
    assert all(value==0 for value in counts(sessions).values())

def concurrent(run,n=6):
    barrier=Barrier(n)
    def work(_):
        barrier.wait(timeout=10)
        return run()
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures=[executor.submit(work,i) for i in range(n)]
        return [f.result(timeout=20) for f in futures]

def test_concurrent_issue_retries_create_one_slate(store):
    service,sessions,_=store
    p,c,m,b=setup();r=rank_candidates(b,m,c,profile=p);a=actor();key=uuid4()
    results=concurrent(lambda:service.issue(a,key,r,c,retrieval_batch=b,simulated=True))
    assert len({v["decision_id"] for v in results})==1
    assert counts(sessions)["recommendation_decisions"]==counts(sessions)["recommendation_items"]==1

def test_concurrent_visibility_and_action_retries(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    outputs=concurrent(lambda:service.acknowledge(a,ack(item)))
    assert len({v["id"] for v in outputs})==1
    request=action(item)
    outputs=concurrent(lambda:service.action(a,request))
    assert len({v["id"] for v in outputs})==1
    assert counts(sessions)["recommendation_impressions"]==counts(sessions)["interaction_events"]==1

def test_disposing_engine_does_not_lose_events(store):
    service,sessions,engine=store
    a,_,_,_,_,item,_=issue(service);v=ack(item)
    first=service.acknowledge(a,v)
    engine.dispose()
    new=EventService(events_sessions(engine))
    assert new.acknowledge(a,v)["id"]==first["id"]
    assert counts(sessions)["recommendation_impressions"]==1

def test_migration_matches_orm_and_foreign_keys_are_real(store):
    _,sessions,engine=store
    with engine.connect() as c:
        assert compare_metadata(MigrationContext.configure(c),Base.metadata)==[]
        assert c.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()=="0002_event_protocol"
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(Impression(item_id=uuid4(),visible_ms=1200,visible_fraction=.8,source="client_visibility_ack"))

def test_query_text_and_identifiers_are_not_copied_to_decision_snapshot(store):
    service,sessions,_=store
    p,c,m,b=setup(task="НДС email@example.com 127.0.0.1")
    r=rank_candidates(b,m,c,profile=p)
    result=service.issue(actor(),uuid4(),r,c,retrieval_batch=b,simulated=True)
    with sessions() as db:
        raw=json.dumps(db.get(Decision,UUID(result["decision_id"])).snapshot)
        assert "email@example.com" not in raw and "127.0.0.1" not in raw
        assert p.user_key not in raw

def test_concurrent_payment_rekeys_still_make_one_transaction(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service);service.acknowledge(a,ack(item))
    request=purchase(item);principal=PaymentPrincipal(provider="gateway")
    values=concurrent(lambda:service.purchase(a,request.model_copy(update={"event_key":uuid4()}),principal))
    assert len({v["id"] for v in values})==1
    assert counts(sessions)["interaction_events"]==1

def test_cross_actor_concurrent_transaction_has_one_winner(store):
    service,sessions,_=store
    a,_,_,_,_,one,_=issue(service);b,_,_,_,_,two,_=issue(service)
    service.acknowledge(a,ack(one));service.acknowledge(b,ack(two))
    barrier=Barrier(2);transaction="shared-"+uuid4().hex
    def run(actor,item):
        barrier.wait(timeout=10)
        try:
            service.purchase(actor,purchase(item,transaction_key=transaction),PaymentPrincipal(provider="gateway"))
            return "accepted"
        except EventConflict:return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        tasks=[executor.submit(run,a,one),executor.submit(run,b,two)]
        assert sorted(t.result(timeout=20) for t in tasks)==["accepted","conflict"]
    assert counts(sessions)["interaction_events"]==1

def test_purchase_sql_constraint_rejects_null_amount(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service)
    imp=service.acknowledge(a,ack(item))
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(Interaction(actor_id=a.actor_id,session_id=a.session_id,item_id=UUID(item["item_id"]),
                impression_id=UUID(imp["id"]),kind="purchase_confirmed",source="payment_server",trust="server_verified",
                simulated=True,is_free_open=False,qualified_use=False,provider="gateway",payment_environment="test",
                transaction_key="null-amount",amount=None,currency="RUB",payment_hash="a"*64))

def test_unknown_stored_protocol_cannot_be_replayed(store):
    service,sessions,_=store
    a,_,_,_,_,item,_=issue(service);request=ack(item)
    service.acknowledge(a,request)
    with sessions.begin() as db:
        receipt=db.scalar(select(MessageReceipt).where(MessageReceipt.event_key==request.event_key))
        receipt.protocol_version="future"
    with pytest.raises(EventConflict):service.acknowledge(a,request)

def test_same_chunk_id_cannot_hide_modified_source_score(store):
    service,sessions,_=store
    p,c,m,b=setup();r=rank_candidates(b,m,c,profile=p)
    r.candidates[0].citations[0].raw_score+=.01
    with pytest.raises(EventConflict,match="witnesses"):
        service.issue(actor(),uuid4(),r,c,retrieval_batch=b,simulated=True)
    assert counts(sessions)["recommendation_decisions"]==0
