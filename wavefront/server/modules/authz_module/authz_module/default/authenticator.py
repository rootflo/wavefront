"""Generic authenticators services compose their defaults from."""

from __future__ import annotations

from typing import Sequence

from starlette.requests import HTTPConnection

from authz_module.principal import Principal
from authz_module.protocols import Authenticator


class AnonymousAuthenticator:
    """Never finds credentials: every non-public route is refused."""

    async def authenticate(self, conn: HTTPConnection) -> Principal | None:
        return None


class ChainAuthenticator:
    """Try each authenticator in turn; the first principal wins.

    An ``AuthenticationError`` from any of them stops the chain: credentials
    that were presented and failed are not retried as something else.
    """

    def __init__(self, authenticators: Sequence[Authenticator]):
        self.authenticators = tuple(authenticators)

    async def authenticate(self, conn: HTTPConnection) -> Principal | None:
        for authenticator in self.authenticators:
            principal = await authenticator.authenticate(conn)
            if principal is not None:
                return principal
        return None
