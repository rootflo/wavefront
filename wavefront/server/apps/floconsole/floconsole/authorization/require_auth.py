from dataclasses import dataclass

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse

from floconsole.constants.auth import AUTH_ROLE_ID
from floconsole.di.application_container import ApplicationContainer
from floconsole.db.models.session import Session
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.services.token_service import TokenService

import jwt
from starlette.middleware.base import BaseHTTPMiddleware

optional_auth_apis = [
    '/floconsole/v1/health',
    '/floconsole/v1/authenticate',
    '/',
    '/docs',
    '/openapi.json',
]


@dataclass
class UserSession:
    role_id: str
    user_id: str
    session_id: str


class RequireAuthMiddleware(BaseHTTPMiddleware):
    @inject
    async def dispatch(
        self,
        request: Request,
        call_next,
        token_service: TokenService = Provide[ApplicationContainer.token_service],
        response_formatter: ResponseFormatter = Provide[
            CommonContainer.response_formatter
        ],
        session_repository: SQLAlchemyRepository[Session] = Provide[
            ApplicationContainer.session_repository
        ],
    ):
        try:
            if request.method == 'OPTIONS':
                return await call_next(request)

            authorization = request.headers.get('Authorization')

            token = None
            if authorization and authorization.startswith('Bearer '):
                token = authorization.split(' ')[1]
            if request.url.path in optional_auth_apis:
                return await call_next(request)

            elif token is None:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=response_formatter.buildErrorResponse(
                        error='Token missing in request'
                    ),
                )

            try:
                decoded = token_service.decode_token(token)
            except ValueError as e:
                logger.error(f'Token validation error: {e}')
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=response_formatter.buildErrorResponse(
                        error='Invalid token format'
                    ),
                )
            if 'session_id' not in decoded:
                logger.error('Invalid token: missing session_id')
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=response_formatter.buildErrorResponse(
                        error='Invalid token: session not found'
                    ),
                )

            if 'role_id' not in decoded or decoded['role_id'] != AUTH_ROLE_ID:
                logger.error('Invalid token: Not the console user')
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=response_formatter.buildErrorResponse(
                        error='Invalid token: Not the console user'
                    ),
                )

            # If not in cache, fetch from DB
            session = await session_repository.find_one(id=decoded['session_id'])
            if not session:
                logger.error('Invalid session: session not found in database')
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=response_formatter.buildErrorResponse(
                        error='Invalid session'
                    ),
                )

            if str(session.user_id) != decoded['user_id']:
                logger.error('Invalid session: session does not belong to user')
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content=response_formatter.buildErrorResponse(
                        error='Invalid session'
                    ),
                )

            session_obj = UserSession(
                role_id=decoded['role_id'],
                user_id=decoded['user_id'],
                session_id=decoded['session_id'],
            )
            request.state.session = session_obj

            response = await call_next(request)
            return response

        except jwt.ExpiredSignatureError as exc:
            logger.error(f'ExpiredSignatureError in require_auth middleware: {exc}')
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=response_formatter.buildErrorResponse(
                    error='Token has expired. Please log in again.'
                ),
            )
