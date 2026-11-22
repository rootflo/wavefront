import uuid
from typing import Optional, Tuple

from fastapi import Request
from user_management_module.constants.auth import RootfloHeaders


class NotAUserError(Exception):
    """The caller is authenticated but is not a human user."""


def current_user_id(request: Request) -> uuid.UUID:
    """Resolve the caller's user id as a UUID.

    `request.state.session.user_id` is a raw JWT claim, so it arrives as a
    `str` -- comparing it directly against the uuid `chat_sessions.user_id`
    column would never match and every owned-session lookup would 404.

    Service identities (service tokens, mTLS, HMAC, passthrough) carry
    sentinels like 'service' or 'hmac-service' rather than a uuid. A chat
    session belongs to a person, so those callers are rejected instead of being
    coerced into a fabricated owner.
    """
    raw = getattr(request.state.session, 'user_id', None)
    if isinstance(raw, uuid.UUID):
        return raw
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NotAUserError(
            'Chat sessions require an end-user identity; '
            'service credentials cannot own a conversation'
        ) from exc


def caller_credentials(request: Request) -> Tuple[Optional[str], Optional[str]]:
    """The caller's bearer token and app key, for an agent's tools to act with.

    An agent-backed chatbot runs tools on the caller's behalf, so those tools
    must carry the caller's own credentials and not the service's: the chat is
    not a way to do what the user's account cannot.

    Mirrors agents_module's extract_auth_credentials, which this module does
    not depend on.
    """
    access_token = None
    auth_header = request.headers.get('Authorization')
    if auth_header:
        parts = auth_header.split(' ', 1)
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            access_token = parts[1]

    return access_token, request.headers.get(RootfloHeaders.CLIENT_KEY)
