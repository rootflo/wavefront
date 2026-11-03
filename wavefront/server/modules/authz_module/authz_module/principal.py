"""The identity a request runs as."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class PrincipalType(str, Enum):
    USER = 'user'
    SERVICE = 'service'
    AGENT = 'agent'
    ANONYMOUS = 'anonymous'


def _frozen(mapping: Mapping[str, str] | None) -> Mapping[str, str]:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True)
class Principal:
    """Who is making a request.

    ``role_id`` is the role a session token carries. Only the default
    authorizer reads it; other providers decide from their own data.

    ``delegation`` lists the principals this one acts on behalf of, outermost
    first, for a call made by one principal for another (an agent invoked by a
    user, say). It is empty for a direct call.
    """

    id: str
    type: PrincipalType
    app_id: str | None = None
    session_id: str | None = None
    role_id: str | None = None
    attributes: Mapping[str, str] = field(default_factory=lambda: _frozen(None))
    delegation: tuple['Principal', ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.attributes, MappingProxyType):
            object.__setattr__(self, 'attributes', _frozen(self.attributes))

    # Callers written against the old session object read ``user_id``.
    @property
    def user_id(self) -> str:
        return self.id

    @property
    def is_anonymous(self) -> bool:
        return self.type is PrincipalType.ANONYMOUS

    @property
    def is_service(self) -> bool:
        return self.type is PrincipalType.SERVICE


ANONYMOUS = Principal(id='anonymous', type=PrincipalType.ANONYMOUS)


def user_principal(
    user_id: str,
    *,
    role_id: str | None = None,
    session_id: str | None = None,
    app_id: str | None = None,
    attributes: Mapping[str, str] | None = None,
) -> Principal:
    return Principal(
        id=str(user_id),
        type=PrincipalType.USER,
        role_id=role_id,
        session_id=session_id,
        app_id=app_id,
        attributes=_frozen(attributes),
    )


def service_principal(
    service_id: str,
    *,
    role_id: str | None = None,
    session_id: str | None = None,
    attributes: Mapping[str, str] | None = None,
) -> Principal:
    return Principal(
        id=service_id,
        type=PrincipalType.SERVICE,
        role_id=role_id,
        session_id=session_id,
        attributes=_frozen(attributes),
    )
