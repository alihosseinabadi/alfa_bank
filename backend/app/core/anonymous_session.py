"""Signed, expiring anonymous identity and a session-bound CSRF token."""
from datetime import datetime, timezone
import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

from app.schemas.events import TrustedActor

COOKIE_NAME = 'alfa_anon_session'
SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


class InvalidSession(ValueError):
    pass


def _mac(secret: str, purpose: str, value: str) -> str:
    return hmac.new(secret.encode('utf-8'), f'{purpose}:{value}'.encode('ascii'), hashlib.sha256).hexdigest()


def issue_cookie(secret: str) -> str:
    payload = f'v1.{uuid4().hex}.{int(datetime.now(timezone.utc).timestamp()) + SESSION_TTL_SECONDS}'
    return f'{payload}.{_mac(secret, "session", payload)}'


def read_cookie(secret: str, cookie: str) -> TrustedActor:
    if len(cookie) > 160:
        raise InvalidSession('invalid session')
    parts = cookie.split('.')
    if (len(parts) != 4 or parts[0] != 'v1' or len(parts[3]) != 64
            or any(c not in '0123456789abcdef' for c in parts[3])):
        raise InvalidSession('invalid session')
    payload = '.'.join(parts[:3])
    try:
        if not hmac.compare_digest(parts[3], _mac(secret, 'session', payload)):
            raise InvalidSession('invalid session')
        actor_id = UUID(hex=parts[1])
        expires = int(parts[2])
        if actor_id.version != 4 or len(parts[1]) != 32 or expires <= int(datetime.now(timezone.utc).timestamp()):
            raise InvalidSession('invalid session')
    except (ValueError, OverflowError, UnicodeError):
        raise InvalidSession('invalid session') from None
    return TrustedActor(actor_id=actor_id, session_id=actor_id, kind='anonymous')


def csrf_token(secret: str, cookie: str) -> str:
    return _mac(secret, 'csrf', cookie)


def valid_csrf(secret: str, cookie: str, candidate: str) -> bool:
    return (len(candidate) == 64 and all(c in '0123456789abcdef' for c in candidate)
            and secrets.compare_digest(csrf_token(secret, cookie), candidate))
