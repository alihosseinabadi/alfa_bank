"""Synthetic stage-7 actions over real catalog cards; no real payment or reward."""
import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID,uuid4
from sqlalchemy import select,func
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.database.connection import events_engine,events_sessions
from app.services.event_service import EventService,VisibilityRequired
from app.schemas.events import TrustedActor,VisibilityAck,ClientAction,PaymentNotice,PaymentPrincipal
from app.models.events import Decision,DecisionItem,Impression,Interaction,MessageReceipt
from app.data_preparation.ranking_bundle import load_ranking_catalog,load_ranking_context
from app.ml.profile_contracts import ExplicitConstraints
from app.ml.prior_ranking import rank_candidates
from rank_materials import retrieve_batch

def summary(sessions,actor):
    with sessions() as db:
        decisions=db.scalar(select(func.count()).select_from(Decision).where(Decision.actor_id==actor.actor_id))
        items=db.scalar(select(func.count()).select_from(DecisionItem).join(Decision).where(Decision.actor_id==actor.actor_id))
        visible=db.scalar(select(func.count()).select_from(Impression).join(DecisionItem).join(Decision).where(Decision.actor_id==actor.actor_id))
        events=db.scalars(select(Interaction).where(Interaction.actor_id==actor.actor_id)).all()
        receipts=db.scalar(select(func.count()).select_from(MessageReceipt).where(MessageReceipt.actor_id==actor.actor_id))
        kinds={kind:sum(e.kind==kind for e in events) for kind in ("click","material_open","purchase_intent","purchase_confirmed")}
        return {"decisions":decisions,"issued_items":items,"visible_impressions":visible,
                "events":kinds,"receipts":receipts,"all_events_simulated":all(e.simulated for e in events),
                "qualified_uses":sum(e.qualified_use for e in events)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=["issue","actions","verify"])
    p.add_argument("--receipt",type=Path,default=ROOT/"reports/stage7_demo_v1_receipt.json")
    args=p.parse_args()
    target=args.receipt.resolve()
    if not any(target.is_relative_to((ROOT/folder).resolve()) for folder in ("reports","artifacts","data/processed")):
        p.error("Receipt must stay in a private ignored project directory")
    engine=events_engine();sessions=events_sessions(engine);service=EventService(sessions)
    saved=json.loads(target.read_text()) if target.exists() else None
    if args.phase=="issue":
        if saved is None:
            saved={"actor":TrustedActor(actor_id=uuid4(),session_id=uuid4(),kind="anonymous").model_dump(mode="json"),
                "request_key":str(uuid4()),"keys":{k:str(uuid4()) for k in ("visibility","click","material_open","purchase_intent","purchase_confirmed")},
                "transaction_key":"synthetic-"+uuid4().hex}
        actor=TrustedActor.model_validate(saved["actor"])
        index,manifest,materials=load_ranking_catalog(ROOT/"artifacts/retrieval",ROOT/"data/processed/catalog")
        profile,context,progress=load_ranking_context(materials,manifest,"Управление командой",ExplicitConstraints(formats=["course"]))
        batch=retrieve_batch(index,manifest,context,SimpleNamespace(method="tfidf"))
        ranking=rank_candidates(batch,materials,context,profile=profile,progress=progress,k=2)
        if not ranking.candidates:raise RuntimeError("The real-catalog demo needs at least one candidate")
        saved["decision"]=service.issue(actor,UUID(saved["request_key"]),ranking,context,retrieval_batch=batch,simulated=True)
        target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
    else:
        if saved is None:p.error("Run issue first")
        actor=TrustedActor.model_validate(saved["actor"])
        if args.phase=="actions":
            item=saved["decision"]["items"][0]
            keys=saved["keys"]
            def action(kind):
                return ClientAction(event_key=keys[kind],item_id=item["item_id"],material_key=item["material_key"],kind=kind)
            try:service.action(actor,action("click"))
            except VisibilityRequired:saved["pre_ack_action_rejected"]=True
            ack=VisibilityAck(event_key=keys["visibility"],item_id=item["item_id"],material_key=item["material_key"],
                              visible_ms=1500,visible_fraction=.9)
            first=service.acknowledge(actor,ack);assert service.acknowledge(actor,ack)["id"]==first["id"]
            for kind in ("click","material_open","purchase_intent"):
                req=action(kind);first=service.action(actor,req);assert service.action(actor,req)["id"]==first["id"]
            payment=PaymentNotice(event_key=keys["purchase_confirmed"],item_id=item["item_id"],material_key=item["material_key"],
                transaction_key=saved["transaction_key"],amount="100.00",currency="RUB")
            principal=PaymentPrincipal(provider="synthetic_demo",environment="test")
            first=service.purchase(actor,payment,principal);assert service.purchase(actor,payment,principal)["id"]==first["id"]
            target.write_text(json.dumps(saved,ensure_ascii=False,indent=2))
    result=summary(sessions,actor)
    result["phase"]=args.phase;result["synthetic_actions"]=True
    result["pre_ack_action_rejected"]=saved.get("pre_ack_action_rejected",False)
    if args.phase=="verify":
        assert result["decisions"]==1 and result["visible_impressions"]==1
        assert all(n==1 for n in result["events"].values()) and result["receipts"]==5
        assert result["all_events_simulated"] and result["qualified_uses"]==0
        (ROOT/"reports/stage7_demo_summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    engine.dispose()
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
