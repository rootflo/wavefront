import uuid

from fastapi import Request


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
