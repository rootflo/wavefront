from uuid import uuid4

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from floconsole.utils.password_utils import verify_password_async
from floconsole.constants.auth import AUTH_ROLE_ID
from floconsole.db.models.user import User
from floconsole.db.models.session import Session
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.di.application_container import ApplicationContainer
from floconsole.services.token_service import TokenService

auth_router = APIRouter(prefix='/v1')


class AuthRequest(BaseModel):
    email: str
    password: str


@auth_router.post('/authenticate')
@inject
async def authenticate(
    request: Request,
    auth_data: AuthRequest,
    token_service: TokenService = Depends(Provide[ApplicationContainer.token_service]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[ApplicationContainer.session_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    user = await user_repository.find_one(email=auth_data.email)
    if user is None or not await verify_password_async(
        auth_data.password, user.password
    ):
        # Handle failed login attempt
        # No email in logs: it is personal data, and failed logins are routine.
        logger.warning('Authentication failed: unknown email or wrong password')
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Incorrect username or password'
            ),
        )
    if user.deleted:
        logger.warning(f'Authentication attempt for disabled user {user.id}')
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('User account is disabled'),
        )

    # Get device info from headers
    device_info = request.headers.get('User-Agent')

    # Sign the token BEFORE touching existing sessions: if signing fails (KMS
    # down, kms pool busy) the user keeps their current session instead of
    # ending up logged out with no replacement.
    session_id = uuid4()
    token = await token_service.create_token_async(
        sub=user.email,
        user_id=str(user.id),
        role_id=AUTH_ROLE_ID,
        payload={'session_id': str(session_id)},
        expiry=token_service.token_expiry,
    )

    # bcrypt and signing ran off the event loop, so a password change or an
    # account disable can land in between. Only admit the login if the
    # credential it was checked against is still the current one.
    current = await user_repository.find_one(id=user.id)
    if current is None or current.deleted or current.password != user.password:
        logger.warning(
            f'Login for user {user.id} rejected: account changed during login'
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Incorrect username or password'
            ),
        )

    await session_repository.delete_all(user_id=user.id)

    # Create new session
    await session_repository.create(
        user_id=user.id, device_info=device_info, id=session_id
    )

    response_data = {'access_token': token, 'token_type': 'bearer'}

    logger.info(f'User {auth_data.email} authenticated successfully')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': response_data}),
    )


@auth_router.post('/logout')
@inject
async def logout(
    request: Request,
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[ApplicationContainer.session_repository]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    # Get the current session from request state
    current_session = request.state.session

    # Delete the session from database
    await session_repository.delete_all(id=current_session.session_id)

    logger.info(f'User logged out successfully - session: {current_session.session_id}')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Successfully logged out'}
        ),
    )
