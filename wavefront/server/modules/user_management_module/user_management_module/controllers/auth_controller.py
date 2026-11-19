from typing import Optional
from uuid import uuid4

from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from authlib.integrations.starlette_client import OAuth
from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import (
    INACTIVE_ACCOUNT_DISABLE_FLAG,
    FeatureFlags,
)
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from db_repo_module.cache.cache_manager import CacheManager, CacheUnavailableError
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
from pydantic import EmailStr
from pydantic import Field
from pydantic import field_validator
from user_management_module.models.oauth_provider import OAuthProviderConfig
from user_management_module.models.user_schema import (
    EMAIL_MAX_LENGTH,
    PASSWORD_MAX_LENGTH,
    TOKEN_MAX_LENGTH,
)
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.services.account_inactivity_service import (
    AccountInactivityService,
)
from user_management_module.services.recaptcha_service import (
    RECAPTCHA_ACTION_LOGIN,
    RecaptchaService,
)
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from user_management_module.utils.password_utils import verify_password_async
from user_management_module.utils.user_utils import create_account_lockout_response
from user_management_module.constants.cache import get_session_cache_key
from user_management_module.utils.user_utils import normalize_email

auth_router = APIRouter(prefix='/v1')
oauth = OAuth()


class AuthRequest(BaseModel):
    email: EmailStr = Field(..., max_length=EMAIL_MAX_LENGTH)
    password: str = Field(..., min_length=1, max_length=PASSWORD_MAX_LENGTH)
    recaptcha_token: Optional[str] = Field(None, max_length=TOKEN_MAX_LENGTH)

    @field_validator('email')
    @classmethod
    def lowercase_email(cls, v):
        return normalize_email(v)


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
    recaptcha_service: RecaptchaService = Depends(
        Provide[UserContainer.recaptcha_service]
    ),
    feature_flags: FeatureFlags = Depends(Provide[CommonContainer.feature_flags]),
):
    is_recaptcha_valid, recaptcha_error = await recaptcha_service.verify(
        auth_data.recaptcha_token, action=RECAPTCHA_ACTION_LOGIN
    )
    if not is_recaptcha_valid:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                recaptcha_error or 'reCAPTCHA verification failed'
            ),
        )

    user = await user_repository.find_one(email=normalize_email(auth_data.email))

    if user:
        is_locked, locked_until = await account_lockout_service.check_account_lockout(
            user
        )
        if is_locked:
            if not await verify_password_async(auth_data.password, user.password):
                await account_lockout_service.record_locked_attempt(user)
            return create_account_lockout_response(
                locked_until, account_lockout_service, response_formatter
            )

    # Check for account inactivity if feature is enabled and user exists
    if user and feature_flags.enabled(INACTIVE_ACCOUNT_DISABLE_FLAG):
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

    if user is None or not await verify_password_async(
        auth_data.password, user.password
    ):
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

    # Sign the token BEFORE touching existing sessions: if signing fails (KMS
    # down, kms pool busy) the user keeps their current session instead of
    # ending up logged out with no replacement. The session id is chosen up
    # front so the token can carry it.
    session_id = uuid4()
    token = await token_service.create_token_async(
        sub=user.email,
        user_id=str(user.id),
        role_id=role_id,
        payload={'session_id': str(session_id)},
        expiry=token_service.token_expiry,
    )

    await user_service.invalidate_user_sessions(str(user.id))

    # Create new session
    await session_repository.create(
        user_id=user.id, device_info=device_info, id=session_id
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

    session_cache_key = get_session_cache_key(current_session.session_id)

    # The middleware trusts a cached session before the database, so the DB
    # delete is wrapped in a cache invalidation: strict before it (Redis down:
    # 503 with nothing changed, retry-safe), best-effort after it, and fills
    # that raced the logout can never bring the session back.
    try:
        async with cache_manager.invalidating(
            current_session.user_id, session_cache_key
        ):
            await session_repository.delete_all(id=current_session.session_id)
    except CacheUnavailableError as e:
        logger.error(f'Logout could not invalidate the cached session: {e}')
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response_formatter.buildErrorResponse(
                'Logout could not be completed. Please try again shortly.'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Successfully logged out'}
        ),
    )
