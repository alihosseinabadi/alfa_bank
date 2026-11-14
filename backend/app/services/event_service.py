"""Atomic decisions, reported visibility and actions. No reward or model updates."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select,func
from sqlalchemy.dialects.postgresql import insert
from app.models.events import Actor,Decision,DecisionItem,Impression,Interaction,MessageReceipt
from app.ml.feature_registry import REGISTRY_HASH,validate_features
from app.ml.profile_policy import fingerprint
from urllib.parse import urlsplit
from app.schemas.events import TrustedActor,VisibilityAck,ClientAction,PaymentPrincipal,PaymentNotice

class EventConflict(ValueError):pass
class ItemNotFound(ValueError):pass
class VisibilityRequired(ValueError):pass
class InvalidEventTime(ValueError):pass

def canonical(value):
    if isinstance(value,datetime):return value.astimezone(timezone.utc).isoformat()
    if isinstance(value,UUID):return str(value)
    if isinstance(value,Decimal):return format(value.quantize(Decimal(".01")),".2f")
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [canonical(v) for v in value]
    return value

class EventService:
    def __init__(self,sessions,*,allow_live_payments=False):
        self.sessions=sessions
        self.allow_live_payments=allow_live_payments

    def _now(self):return datetime.now(timezone.utc)

    def _lock_actor(self,db,actor):
        db.execute(insert(Actor).values(id=actor.actor_id,kind=actor.kind,
            anonymous_session_id=actor.session_id if actor.kind=="anonymous" else None).on_conflict_do_nothing())
        row=db.scalar(select(Actor).where(Actor.id==actor.actor_id).with_for_update())
        if row.kind!=actor.kind or (row.kind=="anonymous" and row.anonymous_session_id!=actor.session_id):
            raise EventConflict("Trusted actor/session identity changed")

    def _time(self,value,days=7):
        if value is not None and not self._now()-timedelta(days=days)<=value<=self._now()+timedelta(minutes=5):
            raise InvalidEventTime("Reported time outside accepted ingestion range")

    def _owned(self,db,actor,item_id,material_key):
        found=db.execute(select(DecisionItem,Decision).join(Decision,Decision.id==DecisionItem.decision_id)
            .where(DecisionItem.id==item_id,Decision.actor_id==actor.actor_id)).first()
        if found is None or found[0].material_key!=material_key:
            raise ItemNotFound("Issued item not found for this actor/material")
        return found

    def _replay(self,db,actor,event_key,kind,payload_hash):
        row=db.scalar(select(MessageReceipt).where(MessageReceipt.actor_id==actor.actor_id,
                                                   MessageReceipt.event_key==event_key))
        if row is None:return None
        if row.protocol_version!="events-v1" or row.payload_hash!=payload_hash or row.message_type!=kind:
            raise EventConflict("Event key reused with different contents")
        result={"id":str(row.impression_id or row.interaction_id),"replayed":True}
        if row.interaction_id is not None:
            result["impression_id"]=str(db.get(Interaction,row.interaction_id).impression_id)
        return result

    def _receipt(self,db,actor,event_key,kind,payload_hash,*,impression=None,event=None):
        db.add(MessageReceipt(actor_id=actor.actor_id,event_key=event_key,message_type=kind,payload_hash=payload_hash,
            impression_id=impression.id if impression is not None else None,interaction_id=event.id if event is not None else None))
        db.flush()

    def _impression(self,db,item_id,requested=None):
        row=db.scalar(select(Impression).where(Impression.item_id==item_id))
        if row is None:raise VisibilityRequired("A visibility acknowledgement is required; retry the action afterwards")
        if requested is not None and requested!=row.id:raise ItemNotFound("Impression does not match the issued item")
        return row

    def _insert_items(self,db,decision,items):
        for item in items:
            db.add(DecisionItem(decision_id=decision.id,**item))
        db.flush()

    def issue(self,actor,request_key,result,context,*,retrieval_batch,simulated=False):
        if result.context_id!=context.context_id or result.profile_version!=context.profile_version:
            raise EventConflict("Ranking/context mismatch")
        if result.feature_registry_hash!=REGISTRY_HASH or len(result.candidates)>50:
            raise EventConflict("Incompatible ranking feature contract")
        if (retrieval_batch.context_id!=result.context_id or retrieval_batch.index_bundle_id!=result.index_bundle_id
                or retrieval_batch.catalog_bundle_id!=result.catalog_bundle_id
                or retrieval_batch.retrieval_policy_id!=result.retrieval_policy_id
                or retrieval_batch.method!=result.retrieval_method
                or retrieval_batch.retrieval_parameters!=result.retrieval_parameters):
            raise EventConflict("Exact retrieval batch does not match the ranking")
        source_hits={h.material_key:h for h in retrieval_batch.hits}
        metadata={k:getattr(result,k) for k in ("version","context_id","profile_version","index_bundle_id",
            "catalog_bundle_id","retrieval_policy_id","feature_registry_hash","policy_id","retrieval_method","retrieval_parameters","status")}
        context_snapshot={"query_sha256":fingerprint(context.query_text),"query_source":context.query_source,
            "history_weight":context.history_weight,"formats":context.formats,
            "available_time_minutes":context.available_time_minutes,"budget_preference":context.budget_preference,
            "has_industry":bool(context.industry),"has_stage":bool(context.business_stage),"has_experience":bool(context.experience),
            "mode":context.mode,"cutoff_month":context.cutoff_month}
        items=[]
        for i,card in enumerate(result.candidates,1):
            url=urlsplit(card.url)
            if card.rank!=i or url.scheme not in {"http","https"} or not url.netloc or card.url_state=="unavailable":
                raise EventConflict("Invalid ranked card")
            validate_features(card.features)
            if (card.features.material_key!=card.material_key or card.features.context_id!=result.context_id
                    or card.features.profile_version!=result.profile_version
                    or card.features.catalog_bundle_id!=result.catalog_bundle_id
                    or card.features.index_bundle_id!=result.index_bundle_id
                    or card.features.retrieval_policy_id!=result.retrieval_policy_id):
                raise EventConflict("Card features do not match decision provenance")
            source=source_hits.get(card.material_key)
            if source is None or source.retrieval_rank!=card.retrieval_rank:
                raise EventConflict("Missing original retrieval trace")
            expected={e.channel:{"chunk_id":e.chunk.chunk_id,"source_ids":e.chunk.source_block_ids,
                "raw_score":e.raw_score,"channel_rank":e.channel_rank} for e in source.evidence}
            actual={e.channel:{"chunk_id":e.chunk_id,"source_ids":e.source_block_ids,
                "raw_score":e.raw_score,"channel_rank":e.channel_rank} for e in card.citations}
            if len(card.citations)!=len(expected) or actual!=expected:
                raise EventConflict("Retrieval witnesses changed")
            snapshot={"features":card.features.model_dump(mode="json"),"prior_score":card.prior_score,
                "retrieval_score":source.raw_score,
                "score_components":card.score_components,"retrieval_rank":card.retrieval_rank,
                "channel_evidence":[dict(channel=channel,**expected[channel]) for channel in sorted(expected)]}
            items.append({"material_key":card.material_key,"position":i,"access_type":card.access_type,"snapshot":snapshot})
        if len({i["material_key"] for i in items})!=len(items):raise EventConflict("Duplicate material")
        payload={"metadata":metadata,"context":context_snapshot,"items":items,"simulated":simulated,
                 "selection_mode":"deterministic","action_probability":None}
        identity=fingerprint(payload)
        with self.sessions.begin() as db:
            self._lock_actor(db,actor)
            decision=db.scalar(select(Decision).where(Decision.actor_id==actor.actor_id,Decision.request_key==request_key))
            replayed=decision is not None
            if decision is not None:
                if decision.protocol_version!="events-v1" or decision.payload_hash!=identity:raise EventConflict("Recommendation request key reused with different contents")
            else:
                decision=Decision(actor_id=actor.actor_id,session_id=actor.session_id,request_key=request_key,
                    payload_hash=identity,snapshot={k:v for k,v in payload.items() if k!="items"},simulated=simulated)
                db.add(decision);db.flush()
                self._insert_items(db,decision,items)
            rows=db.scalars(select(DecisionItem).where(DecisionItem.decision_id==decision.id).order_by(DecisionItem.position)).all()
            return {"decision_id":str(decision.id),"replayed":replayed,"items":[
                {"item_id":str(i.id),"material_key":i.material_key,"position":i.position} for i in rows]}

    def acknowledge(self,actor:TrustedActor,request:VisibilityAck):
        identity=fingerprint(canonical(request.model_dump()))
        with self.sessions.begin() as db:
            self._lock_actor(db,actor)
            replay=self._replay(db,actor,request.event_key,"visibility",identity)
            if replay:return replay
            item,decision=self._owned(db,actor,request.item_id,request.material_key)
            self._time(request.client_time)
            impression=db.scalar(select(Impression).where(Impression.item_id==item.id))
            duplicate=impression is not None
            if impression is None:
                impression=Impression(item_id=item.id,client_time=request.client_time,
                    visible_ms=request.visible_ms,visible_fraction=request.visible_fraction)
                db.add(impression);db.flush()
            self._receipt(db,actor,request.event_key,"visibility",identity,impression=impression)
            return {"id":str(impression.id),"replayed":duplicate}

    def action(self,actor:TrustedActor,request:ClientAction):
        identity=fingerprint(canonical(request.model_dump()))
        with self.sessions.begin() as db:
            self._lock_actor(db,actor)
            replay=self._replay(db,actor,request.event_key,request.kind,identity)
            if replay:return replay
            item,decision=self._owned(db,actor,request.item_id,request.material_key)
            impression=self._impression(db,item.id,request.impression_id)
            self._time(request.client_time)
            event=Interaction(actor_id=actor.actor_id,session_id=actor.session_id,item_id=item.id,
                impression_id=impression.id,kind=request.kind,source="client",trust="client_reported",
                simulated=decision.simulated,is_free_open=request.kind=="material_open" and item.access_type=="Открытый",
                qualified_use=False,client_time=request.client_time)
            db.add(event);db.flush()
            self._receipt(db,actor,request.event_key,request.kind,identity,event=event)
            return {"id":str(event.id),"impression_id":str(impression.id),"replayed":False}

    def purchase(self,actor:TrustedActor,request:PaymentNotice,principal:PaymentPrincipal):
        if principal.environment=="production" and not self.allow_live_payments:
            raise EventConflict("Live payment ingestion is disabled")
        identity=fingerprint(canonical({"notice":request.model_dump(),"principal":principal.model_dump()}))
        payment_hash=fingerprint(canonical({"actor_id":actor.actor_id,"item_id":request.item_id,
            "material_key":request.material_key,"provider":principal.provider,"environment":principal.environment,
            "transaction_key":request.transaction_key,"amount":request.amount,"currency":request.currency,
            "occurred_at":request.occurred_at}))
        with self.sessions.begin() as db:
            self._lock_actor(db,actor)
            replay=self._replay(db,actor,request.event_key,"purchase_confirmed",identity)
            if replay:return replay
            item,decision=self._owned(db,actor,request.item_id,request.material_key)
            impression=self._impression(db,item.id,request.impression_id)
            self._time(request.occurred_at,30)
            lock_key=principal.provider+":"+principal.environment+":"+request.transaction_key
            db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key,0))))
            event=db.scalar(select(Interaction).where(Interaction.provider==principal.provider,
                Interaction.payment_environment==principal.environment,Interaction.transaction_key==request.transaction_key))
            duplicate=event is not None
            if event is not None:
                if event.payment_hash!=payment_hash:raise EventConflict("Payment transaction reused with different contents")
            else:
                if principal.environment=="production" and decision.simulated:
                    raise EventConflict("Live payment cannot refer to a simulated decision")
                event=Interaction(actor_id=actor.actor_id,session_id=actor.session_id,item_id=item.id,
                    impression_id=impression.id,kind="purchase_confirmed",source="payment_server",trust="server_verified",
                    simulated=decision.simulated or principal.environment=="test",is_free_open=False,qualified_use=False,
                    client_time=request.occurred_at,provider=principal.provider,payment_environment=principal.environment,
                    transaction_key=request.transaction_key,amount=request.amount,currency=request.currency,payment_hash=payment_hash)
                db.add(event);db.flush()
            self._receipt(db,actor,request.event_key,"purchase_confirmed",identity,event=event)
            return {"id":str(event.id),"impression_id":str(impression.id),"replayed":duplicate}
