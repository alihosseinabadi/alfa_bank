"""Client-reported visibility and actions, never trusted payment notices."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from app.api.recommendations import NO_STORE, trusted_actor
from app.schemas.events import ClientAction, TrustedActor, UnattributedClickRequest, VisibilityAck
from app.services.event_service import EventConflict, EventService, InvalidEventTime, ItemNotFound, VisibilityRequired

router = APIRouter(tags=['events'])


class EventResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: UUID
    impression_id: UUID | None = None
    replayed: bool


def event_service(request: Request) -> EventService:
    provider = getattr(request.app.state, 'recommendation_provider', None)
    if provider is None:
        raise HTTPException(status_code=503, detail='Event service is unavailable', headers=NO_STORE)
    return EventService(provider.sessions)


def handle_event(service, method, actor, payload):
    try:
        return getattr(service, method)(actor, payload)
    except ItemNotFound:
        raise HTTPException(status_code=404, detail='Issued item not found in this session', headers=NO_STORE) from None
    except VisibilityRequired:
        raise HTTPException(status_code=409, detail='Visibility must be confirmed first', headers=NO_STORE) from None
    except EventConflict:
        raise HTTPException(status_code=409, detail='Event key or identity conflict', headers=NO_STORE) from None
    except InvalidEventTime:
        raise HTTPException(status_code=422, detail='Invalid event time', headers=NO_STORE) from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail='Event storage is unavailable', headers=NO_STORE) from None


@router.post('/events/visibility', response_model=EventResponse)
def confirm_visibility(payload: VisibilityAck, response: Response,
                       actor: TrustedActor = Depends(trusted_actor), service: EventService = Depends(event_service)):
    response.headers['Cache-Control'] = 'no-store'
    return handle_event(service, 'acknowledge', actor, payload)


@router.post('/events/unattributed-click', response_model=EventResponse)
def record_unattributed_click(payload: UnattributedClickRequest, response: Response,
                              actor: TrustedActor = Depends(trusted_actor), service: EventService = Depends(event_service)):
    response.headers['Cache-Control'] = 'no-store'
    return handle_event(service, 'unattributed_click', actor, payload)


@router.post('/events/action', response_model=EventResponse)
def record_action(payload: ClientAction, response: Response,
                  actor: TrustedActor = Depends(trusted_actor), service: EventService = Depends(event_service)):
    if payload.kind == 'material_open':
        raise HTTPException(status_code=503, detail='Verified material-open integration is not available', headers=NO_STORE)
    response.headers['Cache-Control'] = 'no-store'
    return handle_event(service, 'action', actor, payload)


@router.post('/interactions/', include_in_schema=False)
def legacy_interaction_unavailable():
    raise HTTPException(status_code=503, detail='Use the session-bound event API', headers=NO_STORE)
