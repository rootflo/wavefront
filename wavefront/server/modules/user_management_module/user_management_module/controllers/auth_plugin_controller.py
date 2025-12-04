import json
from uuid import uuid4
from db_repo_module.models.resource import ResourceScope
from dependency_injector.wiring import inject, Provide
from fastapi import Depends, Request, status, APIRouter, Query
from fastapi.responses import JSONResponse, RedirectResponse
from urllib.parse import urlencode
from pydantic import BaseModel
from typing import Dict, Any, Optional
from uuid import UUID


from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.authenticator import Authenticator
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from plugins_module.plugins_container import PluginsContainer
from plugins_module.services.authenticator_services import (
    get_authenticator_instance,
    get_authenticator_config,
    get_authenticator_with_config,
)
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from user_management_module.utils.password_utils import verify_password
from user_management_module.utils.user_utils import get_session_cache_key

from authenticator import AuthenticatorType
from authenticator.helper import validate_email


auth_plugin_router = APIRouter()


class UnifiedAuthRequest(BaseModel):
    auth_id: str
    credentials: Dict[str, Any]


class OAuthInitRequest(BaseModel):
    auth_id: str


@auth_plugin_router.post('/v1/plugin-auth/authenticate')
@inject
async def unified_authenticate(
    request: Request,
    auth_request: UnifiedAuthRequest,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[UserContainer.session_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[CommonContainer.cache_manager]),
    token_service: TokenService = Depends(Provide[AuthContainer.token_service]),
):
    """Unified authentication endpoint that routes to appropriate authenticator."""

    try:
        # Get authenticator instance and config by ID
        auth_id = UUID(auth_request.auth_id)
        authenticator, config_data = await get_authenticator_with_config(
            auth_id, authenticator_repository
        )

        # Handle not found case (both None)
        if config_data is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'Authenticator {auth_request.auth_id} not found'
                ),
            )

        # Handle disabled case (config exists but instance is None)
        if authenticator is None:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    f'Authenticator {auth_request.auth_id} is not enabled'
                ),
            )

        # Handle email/password authentication separately for existing user validation
        if config_data['auth_type'] == AuthenticatorType.EMAIL_PASSWORD.value:
            return await _handle_email_password_auth(
                auth_request.credentials,
                request,
                response_formatter,
                user_service,
                user_repository,
                session_repository,
                cache_manager,
                token_service,
            )

        # Handle OAuth authentication (Google: {authentication_code, state})
        auth_result = authenticator.authenticate(auth_request.credentials)

        if not auth_result.success:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=response_formatter.buildErrorResponse(
                    auth_result.error or 'Authentication failed'
                ),
            )

        # Create session from auth result
        user = await user_repository.find_one(email=auth_result.user_info.email)
        if user is None:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    "User with email doesn't exist"
                ),
            )
        if user.deleted:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'User account is disabled'
                ),
            )

        # Get device info from headers
        device_info = request.headers.get('User-Agent')

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

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Authentication failed: {str(e)}'
            ),
        )


# For google and microsoft oauth
@auth_plugin_router.post('/v1/plugin-auth/oauth/init')
@inject
async def init_oauth_flow(
    request: Request,
    oauth_request: OAuthInitRequest,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Initialize OAuth flow and return authorization URL."""

    try:
        # Get authenticator instance by ID
        auth_id = UUID(oauth_request.auth_id)
        authenticator = await get_authenticator_instance(
            auth_id, authenticator_repository
        )

        if not authenticator:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=response_formatter.buildErrorResponse(
                    f'Authenticator {oauth_request.auth_id} not configured'
                ),
            )

        # Generate state and get authorization URL
        state = json.dumps({'auth_id': oauth_request.auth_id})
        auth_url = authenticator.get_authorization_url(state)

        if not auth_url:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Authenticator {oauth_request.auth_id} does not support OAuth'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'authorization_url': auth_url, 'state': state}
            ),
        )

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to initialize OAuth flow: {str(e)}'
            ),
        )


@auth_plugin_router.get('/v1/oauth/google/callback')
@inject
async def google_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[UserContainer.session_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[UserContainer.cache_manager]),
    token_service: TokenService = Depends(Provide[AuthContainer.token_service]),
):
    """Handle Google OAuth callback."""
    state_obj = json.loads(state)
    auth_id = state_obj['auth_id']

    return await _handle_oauth_callback(
        auth_id,
        {'authorization_code': code, 'state': state, 'error': error},
        request,
        response_formatter,
        authenticator_repository,
        user_service,
        user_repository,
        session_repository,
        cache_manager,
        token_service,
    )


@auth_plugin_router.get('/v1/oauth/microsoft/callback')
@inject
async def microsoft_oauth_callback(
    request: Request,
    code: Optional[str] = Query(
        ...
    ),  # keeping it optional as in error scenarios we dont get code
    state: str = Query(...),
    error: Optional[str] = Query(None),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[UserContainer.user_repository]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    session_repository: SQLAlchemyRepository[Session] = Depends(
        Provide[UserContainer.session_repository]
    ),
    cache_manager: CacheManager = Depends(Provide[UserContainer.cache_manager]),
    token_service: TokenService = Depends(Provide[AuthContainer.token_service]),
):
    """Handle Microsoft OAuth callback."""
    state_obj = json.loads(state)
    auth_id = state_obj['auth_id']

    return await _handle_oauth_callback(
        auth_id,
        {'authorization_code': code, 'state': state, 'error': error},
        request,
        response_formatter,
        authenticator_repository,
        user_service,
        user_repository,
        session_repository,
        cache_manager,
        token_service,
    )


async def _handle_oauth_callback(
    auth_id: str,
    callback_data: Dict[str, Any],
    request: Request,
    response_formatter: ResponseFormatter,
    authenticator_repository: SQLAlchemyRepository[Authenticator],
    user_service: UserService,
    user_repository: SQLAlchemyRepository[User],
    session_repository: SQLAlchemyRepository[Session],
    cache_manager: CacheManager,
    token_service: TokenService,
) -> RedirectResponse:
    """Common OAuth callback handler."""

    try:
        # Get authenticator instance and config
        auth_uuid = UUID(auth_id)
        authenticator, config_data = await get_authenticator_with_config(
            auth_uuid, authenticator_repository
        )

        # Helper to get failure URL from config
        def get_failure_redirect(error_msg: str) -> RedirectResponse:
            if config_data:
                failure_url = config_data.get('config', {}).get(
                    'client_redirect_failure_url'
                )
                if failure_url:
                    provider = config_data.get('auth_type')
                    params = urlencode({'provider': provider, 'error': error_msg})
                    return RedirectResponse(url=f'{failure_url}?{params}')
            return RedirectResponse(url='about:blank')

        # Handle not found case
        if config_data is None:
            return get_failure_redirect(f'Authenticator {auth_id} not found')

        # Handle disabled case
        if authenticator is None:
            return get_failure_redirect(f'Authenticator {auth_id} is not enabled')

        # Extract redirect URLs
        provider = config_data.get('auth_type')
        success_url = config_data.get('config', {}).get('client_redirect_success_url')
        failure_url = config_data.get('config', {}).get('client_redirect_failure_url')

        # Handle OAuth error from provider
        if callback_data.get('error'):
            if failure_url:
                params = urlencode(
                    {
                        'provider': provider,
                        'error': f'OAuth error: {callback_data["error"]}',
                    }
                )
                return RedirectResponse(url=f'{failure_url}?{params}')
            return RedirectResponse(url='about:blank')

        # Handle OAuth callback
        auth_result = authenticator.handle_callback(callback_data)

        if not auth_result.success:
            if failure_url:
                params = urlencode(
                    {
                        'provider': provider,
                        'error': auth_result.error or 'OAuth authentication failed',
                    }
                )
                return RedirectResponse(url=f'{failure_url}?{params}')
            return RedirectResponse(url='about:blank')

        # Create session from auth result
        user = await user_repository.find_one(email=auth_result.user_info.email)
        if user is None:
            if failure_url:
                params = urlencode(
                    {'provider': provider, 'error': "User with email doesn't exist"}
                )
                return RedirectResponse(url=f'{failure_url}?{params}')
            return RedirectResponse(url='about:blank')

        if user.deleted:
            if failure_url:
                params = urlencode(
                    {'provider': provider, 'error': 'User account is disabled'}
                )
                return RedirectResponse(url=f'{failure_url}?{params}')
            return RedirectResponse(url='about:blank')

        # Get device info from headers
        device_info = request.headers.get('User-Agent')

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
            if failure_url:
                params = urlencode(
                    {'provider': provider, 'error': 'User has no access to the console'}
                )
                return RedirectResponse(url=f'{failure_url}?{params}')
            return RedirectResponse(url='about:blank')

        # Include session_id in token payload
        token = token_service.create_token(
            sub=user.email,
            user_id=str(user.id),
            role_id=role_id,
            payload={'session_id': str(session.id)},
            expiry=token_service.token_expiry,
        )

        # Success: redirect to success URL with access token
        if success_url:
            params = urlencode({'provider': provider, 'access_token': token})
            return RedirectResponse(url=f'{success_url}?{params}')

        return RedirectResponse(url='about:blank')

    except Exception as e:
        # Try to get config for failure URL
        try:
            auth_uuid = UUID(auth_id)
            config_data = await get_authenticator_config(
                auth_uuid, authenticator_repository
            )
            if config_data:
                failure_url = config_data.get('config', {}).get(
                    'client_redirect_failure_url'
                )
                if failure_url:
                    provider = config_data.get('auth_type')
                    params = urlencode(
                        {
                            'provider': provider,
                            'error': f'OAuth callback failed: {str(e)}',
                        }
                    )
                    return RedirectResponse(url=f'{failure_url}?{params}')
        except Exception as e:
            pass

        return RedirectResponse(url='about:blank')


async def _handle_email_password_auth(
    credentials: Dict[str, Any],
    request: Request,
    response_formatter: ResponseFormatter,
    user_service: UserService,
    user_repository: SQLAlchemyRepository[User],
    session_repository: SQLAlchemyRepository[Session],
    cache_manager: CacheManager,
    token_service: TokenService,
) -> JSONResponse:
    """Handle email/password authentication with existing user validation."""

    email = credentials.get('email')
    password = credentials.get('password')

    if not email or not password:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Email and password are required'
            ),
        )

    if not validate_email(email):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('Invalid email format'),
        )

    try:
        # Find user in database
        user = await user_repository.find_one(email=email)

        # Check if user exists first (before accessing any attributes)
        if not user:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=response_formatter.buildErrorResponse(
                    'Incorrect email or password'
                ),
            )

        # Check if user account is disabled
        if user.deleted:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'User account is disabled'
                ),
            )

        # Verify password (user is guaranteed to exist here)
        if not verify_password(password, user.password):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=response_formatter.buildErrorResponse(
                    'Incorrect email or password'
                ),
            )

        # Get device info
        device_info = request.headers.get('User-Agent')

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

        # Create JWT token with session information
        token = token_service.create_token(
            sub=user.email,
            user_id=str(user.id),
            role_id=role_id,
            payload={'session_id': str(session.id), 'auth_provider': 'email_password'},
            expiry=token_service.token_expiry,
        )

        response_data = {
            'access_token': token,
            'token_type': 'bearer',
            'session_id': str(session.id),
            'expires_in': token_service.token_expiry,
        }

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'user': response_data}),
        )

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Authentication failed: {str(e)}'
            ),
        )
