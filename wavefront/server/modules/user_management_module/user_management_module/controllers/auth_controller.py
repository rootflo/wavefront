import json
from uuid import uuid4

from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from authlib.integrations.starlette_client import OAuth
from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import (
    INACTIVE_ACCOUNT_DISABLE_FLAG,
    is_feature_enabled,
)
from common_module.response_formatter import ResponseFormatter
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from user_management_module.models.oauth_provider import OAuthProviderConfig
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.services.account_inactivity_service import (
    AccountInactivityService,
)
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from user_management_module.utils.password_utils import verify_password
from user_management_module.utils.user_utils import create_account_lockout_response
from user_management_module.utils.user_utils import get_session_cache_key

auth_router = APIRouter(prefix='/v1')
oauth = OAuth()


class AuthRequest(BaseModel):
    email: str
    password: str


@auth_router.get('/health')
def health_check():
    return {'status': 'ok'}


@auth_router.post('/authenticate')
@inject
async def authenticate(
    request: Request,
    auth_data: AuthRequest,
    token_service: TokenService = Depends(Provide[AuthContainer.token_service]),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[UserContainer.session_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[CommonContainer.cache_manager]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    account_lockout_service: AccountLockoutService = Depends(
        Provide[UserContainer.account_lockout_service]
    ),
    account_inactivity_service: AccountInactivityService = Depends(
        Provide[UserContainer.account_inactivity_service]
    ),
):
    # Check if account is locked before attempting authentication
    is_locked, locked_until = await account_lockout_service.check_account_lockout(
        auth_data.email
    )
    if is_locked:
        return create_account_lockout_response(
            locked_until, account_lockout_service, response_formatter
        )

    user = await user_repository.find_one(email=auth_data.email)

    # Check for account inactivity if feature is enabled and user exists
    if user and is_feature_enabled(INACTIVE_ACCOUNT_DISABLE_FLAG):
        (
            is_inactive,
            days_since_login,
        ) = await account_inactivity_service.check_account_inactivity(user)
        if is_inactive:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    f'Account has been disabled due to inactivity. Last login was {days_since_login} days ago.'
                ),
            )

    if user is None or not verify_password(auth_data.password, user.password):
        # Handle failed login attempt
        if user:  # Only track attempts for existing users
            (
                is_now_locked,
                locked_until,
            ) = await account_lockout_service.handle_failed_login(user)
            if is_now_locked:
                return create_account_lockout_response(
                    locked_until, account_lockout_service, response_formatter
                )

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Incorrect username or password'
            ),
        )
    if user.deleted:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('User account is disabled'),
        )

    # Reset failed attempts on successful login
    await account_lockout_service.reset_failed_attempts(user)

    # Update last login timestamp
    await account_inactivity_service.update_last_login(user)

    # Get device info from headers
    device_info = request.headers.get('User-Agent')

    existing_sessions = await session_repository.find(user_id=user.id, limit=1000)
    for s in existing_sessions:
        cache_manager.remove(get_session_cache_key(s.id))
    await session_repository.delete_all(user_id=user.id)

    # Create new session
    session = await session_repository.create(
        user_id=user.id, device_info=device_info, id=uuid4()
    )

    # Cache session data
    session_cache_key = get_session_cache_key(session.id)
    session_data = {
        'id': str(session.id),
        'user_id': str(session.user_id),
        'device_info': session.device_info,
    }
    cache_manager.add(
        session_cache_key,
        json.dumps(session_data),
        token_service.token_expiry,
    )

    role_id = await user_service.get_user_role_for_scope(
        user_id=str(user.id), scope=ResourceScope.CONSOLE
    )

    if not role_id:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'User has no access to the console'
            ),
        )

    # Include session_id in token payload
    token = token_service.create_token(
        sub=user.email,
        user_id=str(user.id),
        role_id=role_id,
        payload={'session_id': str(session.id)},
        expiry=token_service.token_expiry,
    )

    response_data = {'access_token': token, 'token_type': 'bearer'}
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': response_data}),
    )


@auth_router.post('/authenticate/config')
@inject
def config_oauth(
    config: OAuthProviderConfig,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    oauth.register(
        name=config.name,
        client_id=config.client_id,
        client_secret=config.client_secret,
        redirect_uri=config.redirect_uri,
        client_kwargs=config.client_kwargs,
        server_metadata_url=config.server_metadata_url,
    )
    response_data = f'{config.name} OAuth provider registered successfully.'
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'message': response_data}),
    )


@auth_router.get('/google/login')
async def google_login(request: Request):
    redirect_uri = str(request.url_for('google_callback'))
    return await oauth.google.authorize_redirect(request, redirect_uri)


@auth_router.get('/google/login/callback')
@inject
async def google_callback(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    token = await oauth.google.authorize_access_token(request)
    user = token['userinfo']
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'user': dict(user)}),
    )


# @auth_router.get('/azure/login')
# @inject
# async def azure_login(
#     request: Request,
#     azure_connector: AzureConnector = Depends(Provide[AuthContainer.azure_connector]),
# ):
#     try:
#         url = azure_connector.get_authorization_url()
#         return RedirectResponse(url=url)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @auth_router.get('/oauth/azure/callback')
# @inject
# async def azure_callback(
#     request: Request,
#     code: str,
#     azure_connector: AzureConnector = Depends(Provide[AuthContainer.azure_connector]),
#     response_formatter: ResponseFormatter = Depends(
#         Provide[CommonContainer.response_formatter]
#     ),
# ):
#     try:
#         token = azure_connector.get_credentials_after_auth(code)
#         creds = azure_connector.get_credentials(token)
#         user = await azure_connector.get_user(creds)
#         return JSONResponse(
#             status_code=status.HTTP_200_OK,
#             content=response_formatter.buildSuccessResponse({'user': user.mail}),
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@auth_router.post('/logout')
@inject
async def logout(
    request: Request,
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[UserContainer.session_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[UserContainer.cache_manager]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    # Get the current session from request state
    current_session = request.state.session

    # Delete the session from database
    await session_repository.delete_all(id=current_session.session_id)

    # Clear both user and session cache
    cache_manager.remove(current_session.user_id)
    cache_manager.remove(get_session_cache_key(current_session.session_id))

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Successfully logged out'}
        ),
    )
