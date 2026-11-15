"""Public API boundary. The real ML provider is connected in the next stage."""
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError

from app.core.anonymous_session import (
    COOKIE_NAME, SESSION_TTL_SECONDS, InvalidSession, csrf_token, issue_cookie,
    read_cookie, valid_csrf,
)
from app.core.config import get_settings
from app.schemas.events import TrustedActor
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse, SessionResponse
from app.services.recommendation_provider import ProviderUnavailable, RequestConflict

router = APIRouter(tags=['recommendations'])
NO_STORE = {'Cache-Control': 'no-store'}


def session_secret() -> str:
    secret = get_settings().session_secret
    if secret is None or len(secret.encode('utf-8')) < 32:
        raise HTTPException(status_code=503, detail='Anonymous sessions are not configured', headers=NO_STORE)
    return secret


def trusted_actor(
    cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    csrf: str | None = Header(default=None, alias='X-CSRF-Token'),
    secret: str = Depends(session_secret),
) -> TrustedActor:
    if not cookie:
        raise HTTPException(status_code=401, detail='Anonymous session required', headers=NO_STORE)
    try:
        actor = read_cookie(secret, cookie)
    except InvalidSession:
        raise HTTPException(status_code=401, detail='Invalid or expired session', headers=NO_STORE) from None
    if not csrf or not valid_csrf(secret, cookie, csrf):
        raise HTTPException(status_code=403, detail='Invalid CSRF token', headers=NO_STORE)
    return actor


@router.post('/session', response_model=SessionResponse, summary='Create or resume an anonymous session',
             responses={503: {'description': 'Session secret is not configured'}})
def create_session(
    response: Response,
    cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    secret: str = Depends(session_secret),
):
    if cookie:
        try:
            read_cookie(secret, cookie)
        except InvalidSession:
            cookie = None
    if not cookie:
        cookie = issue_cookie(secret)
        response.set_cookie(COOKIE_NAME, cookie, max_age=SESSION_TTL_SECONDS, httponly=True,
                            secure=get_settings().session_cookie_secure, samesite='lax', path='/')
    response.headers['Cache-Control'] = 'no-store'
    return SessionResponse(csrf_token=csrf_token(secret, cookie))


@router.post('/recommendations', response_model=RecommendationResponse,
             summary='Request a persisted recommendation decision',
             responses={401: {'description': 'Session or authenticated identity required'},
                        403: {'description': 'Missing or invalid CSRF token'},
                        409: {'description': 'Request key reused for different input'},
                        502: {'description': 'Provider response violated the public contract'},
                        503: {'description': 'Recommendation provider unavailable'}})
def recommend(
    payload: RecommendationRequest,
    request: Request,
    response: Response,
    actor: TrustedActor = Depends(trusted_actor),
):
    if payload.user_id is not None:
        raise HTTPException(status_code=401, detail='Authenticated user identity is not available', headers=NO_STORE)
    provider = getattr(request.app.state, 'recommendation_provider', None)
    if provider is None:
        raise HTTPException(status_code=503, detail='Recommendation service is not configured', headers=NO_STORE)
    try:
        result = provider.recommend(actor, payload)
        # Strictly validate the boundary before responding; never serialize internal ML fields.
        public = RecommendationResponse.model_validate(result)
        constraints = payload.constraints
        invalid = len(public.items) > payload.limit or any(
            (constraints.formats and item.format not in constraints.formats)
            or (constraints.budget_preference == 'free_only' and
                (item.access_type != 'Открытый' or (item.listed_price is not None and item.listed_price > 0)))
            or (constraints.available_time_minutes is not None and item.duration_minutes is not None
                and item.duration_minutes > constraints.available_time_minutes)
            for item in public.items
        )
        if invalid:
            raise HTTPException(status_code=502, detail='Invalid recommendation service response', headers=NO_STORE)
    except ProviderUnavailable:
        raise HTTPException(status_code=503, detail='Recommendation service is unavailable', headers=NO_STORE) from None
    except RequestConflict:
        raise HTTPException(status_code=409, detail='Request key reused with different input', headers=NO_STORE) from None
    except ValidationError:
        raise HTTPException(status_code=502, detail='Invalid recommendation service response', headers=NO_STORE) from None
    response.headers['Cache-Control'] = 'no-store'
    return public


@router.get('/recommendations/{user_id}', include_in_schema=False)
def legacy_feed_unavailable(user_id: int):
    raise HTTPException(status_code=503, detail='Recommendation service is not configured', headers=NO_STORE)
