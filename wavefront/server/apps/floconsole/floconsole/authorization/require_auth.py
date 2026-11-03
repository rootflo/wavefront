"""Console request authentication and authorization.

Authentication accepts a console session token only. Authorization is what each
route declares, decided by the provider ``AUTHZ_PROVIDER`` selects; by default
each action's legacy rule, where ``ADMIN`` means a console owner.
"""

from __future__ import annotations

from uuid import UUID

import jwt
from authz_module import (
    AuthenticationError,
    AuthzProvider,
    Principal,
    PrincipalType,
    install,
    load_provider,
)
from authz_module.default import DefaultAuthorizer
from authz_module.middleware import AuthzMiddleware
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import Request, status
from fastapi.responses import JSONResponse

from floconsole.constants.auth import AUTH_ROLE_ID
from floconsole.constants.user import UserRole
from floconsole.db.models.session import Session
from floconsole.db.models.user import User
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.di.application_container import ApplicationContainer
from floconsole.services.token_service import TokenService

PUBLIC_PATHS = ('/', '/docs', '/openapi.json')
TOKEN_EXPIRED = 'Token has expired. Please log in again.'


def render_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ResponseFormatter().buildErrorResponse(error=message),
    )


class ConsoleAuthenticator:
    @inject
    async def authenticate(
        self,
        request: Request,
        token_service: TokenService = Provide[ApplicationContainer.token_service],
        session_repository: SQLAlchemyRepository[Session] = Provide[
            ApplicationContainer.session_repository
        ],
    ) -> Principal | None:
        authorization = request.headers.get('Authorization')
        token = None
        if authorization and authorization.startswith('Bearer '):
            token = authorization.split(' ')[1]
        if token is None:
            return None

        try:
            decoded = token_service.decode_token(token)
        except ValueError as e:
            logger.error(f'Token validation error: {e}')
            raise AuthenticationError('Invalid token format')
        except jwt.ExpiredSignatureError as exc:
            logger.error(f'ExpiredSignatureError in require_auth middleware: {exc}')
            raise AuthenticationError(TOKEN_EXPIRED)

        if 'session_id' not in decoded:
            logger.error('Invalid token: missing session_id')
            raise AuthenticationError('Invalid token: session not found')

        if 'role_id' not in decoded or decoded['role_id'] != AUTH_ROLE_ID:
            logger.error('Invalid token: Not the console user')
            raise AuthenticationError('Invalid token: Not the console user')

        session = await session_repository.find_one(id=decoded['session_id'])
        if not session:
            logger.error('Invalid session: session not found in database')
            raise AuthenticationError('Invalid session')

        if str(session.user_id) != decoded['user_id']:
            logger.error('Invalid session: session does not belong to user')
            raise AuthenticationError('Invalid session')

        return Principal(
            id=decoded['user_id'],
            type=PrincipalType.USER,
            role_id=decoded['role_id'],
            session_id=decoded['session_id'],
        )


class ConsoleLegacyResolver:
    """``ADMIN`` is a console owner; every authenticated caller is a console user."""

    async def is_admin(self, principal: Principal) -> bool:
        return await _is_owner(principal.id)

    async def is_manager(self, principal: Principal) -> bool:
        return False

    async def is_console_user(self, principal: Principal) -> bool:
        return principal.role_id == AUTH_ROLE_ID

    async def has_resource_scope(self, principal: Principal, scope: str) -> bool:
        return False

    def flag_enabled(self, flag: str) -> bool:
        return False


@inject
async def _is_owner(
    user_id: str,
    user_repository: SQLAlchemyRepository[User] = Provide[
        ApplicationContainer.user_repository
    ],
) -> bool:
    user = await user_repository.find_one(id=user_id)
    return bool(user) and user.role == UserRole.OWNER.value


def same_user(a: object, b: object) -> bool:
    try:
        return UUID(str(a)) == UUID(str(b))
    except ValueError:
        return False


def default_provider() -> AuthzProvider:
    return AuthzProvider(
        authenticator=ConsoleAuthenticator(),
        authorizer=DefaultAuthorizer(ConsoleLegacyResolver()),
    )


class RequireAuthMiddleware(AuthzMiddleware):
    def __init__(self, app, *, provider: AuthzProvider | None = None):
        if provider is None:
            provider = load_provider(service='floconsole', default=default_provider())
        install(provider)
        super().__init__(
            app,
            provider=provider,
            render_error=render_error,
            public_paths=PUBLIC_PATHS,
        )

    async def dispatch(self, request: Request, call_next):
        try:
            return await super().dispatch(request, call_next)
        except jwt.ExpiredSignatureError as exc:
            logger.error(f'ExpiredSignatureError in require_auth middleware: {exc}')
            return render_error(status.HTTP_401_UNAUTHORIZED, TOKEN_EXPIRED)
