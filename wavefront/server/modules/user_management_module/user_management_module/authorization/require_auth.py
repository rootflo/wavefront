from dataclasses import dataclass
import json
import hashlib
import hmac
import time
import os
import re

from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.response_formatter import ResponseFormatter
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.session import Session
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Request
from fastapi import status
from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID, RootfloHeaders
from fastapi.responses import JSONResponse
import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from user_management_module.user_container import UserContainer
from user_management_module.utils.user_utils import check_is_admin
from user_management_module.utils.user_utils import get_session_cache_key

optional_auth_apis = [
    '/floware/v1/health',
    '/floware/v1/authenticate',
    '/',
    '/google/login',
    '/google/login/callback',
    '/azure/login',
    '/floware/oauth/azure/callback',
    '/docs',
    '/openapi.json',
    '/floware/v1/user/send-reset-password-email',
    '/floware/v1/user/reset-password',
    '/floware/v1/data-sources/outlook/webhook/email_received',
    '/v1/_metrics',
    '/floware/v1/plugin-auth/authenticate',
    '/floware/v1/oauth/google/callback',
    '/floware/v1/oauth/microsoft/callback',
    '/floware/v1/plugin-auth/oauth/init',
    '/floware/v1/settings/config',
]

hmac_routes = os.getenv('HMAC_AUTH_ROUTES', '').split(',')

floware_jwt_audience = os.getenv('FLOWARE_JWT_AUDIENCE', '')

floware_jwt_validation_issuer = os.getenv('FLOWARE_JWT_VALIDATION_ISSUER', '').split(
    ','
)

console_token_prefix = os.getenv('CONSOLE_TOKEN_PREFIX', 'fc_')
passthrough_secret = os.getenv('PASSTHROUGH_SECRET')
environment = os.getenv('APP_ENV', 'dev')

required_hmac_apis = ['/floware/v1/image/analyse', *hmac_routes]


admin_apis = [
    '/floware/v1/agent-management',
    '/floware/v1/workflow-management',
]


def matches_dynamic_route(path: str, route_pattern: str) -> bool:
    """
    Check if a path matches a dynamic route pattern.

    Args:
        path: The actual request path (e.g., '/floware/v1/workflow-runs/123')
        route_pattern: The route pattern with placeholders (e.g., '/floware/v1/workflow-runs/{workflow_run_id}')

    Returns:
        bool: True if the path matches the pattern, False otherwise
    """
    # Convert route pattern to regex
    # First replace {param} with a placeholder, then escape, then replace placeholder
    regex_pattern = route_pattern
    # Replace {param} with a temporary placeholder
    regex_pattern = re.sub(r'\{[^}]+\}', 'PLACEHOLDER', regex_pattern)
    # Escape the pattern
    regex_pattern = re.escape(regex_pattern)
    # Replace the placeholder with the actual regex pattern
    regex_pattern = regex_pattern.replace('PLACEHOLDER', r'[^/]+')
    regex_pattern = f'^{regex_pattern}$'

    return bool(re.match(regex_pattern, path))


async def validate_service_auth(
    request: Request,
    auth_secrets_repository: SQLAlchemyRepository[AuthSecrets],
    token_service: TokenService,
) -> bool:
    """Validate service-to-service authentication using Client-Key + JWT"""
    try:
        # Get Client-Key header
        client_key = request.headers.get(RootfloHeaders.CLIENT_KEY)
        if not client_key:
            logger.warning('Missing Client-Key header for service auth')
            return False

        # Get Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning('Missing or invalid Authorization header for service auth')
            return False

        token = auth_header.split(' ')[1]

        # Look up client secret using client key
        auth_secret = await auth_secrets_repository.find_one(client_key=client_key)
        if not auth_secret:
            logger.warning(f'Invalid client_key for service auth: {client_key}')
            return False

        # Remove console prefix if present (fc_)
        if token.startswith(console_token_prefix):
            token = token[len(console_token_prefix) :]

        # Validate JWT using client secret (HS256 algorithm for service tokens)
        try:
            decoded = jwt.decode(
                token,
                auth_secret.client_secret,
                algorithms=['HS256'],
                issuer=floware_jwt_validation_issuer or '',
                audience=floware_jwt_audience,
            )

            # For service tokens, we skip session validation
            # Create a minimal session object for compatibility
            request.state.session = UserSession(
                role_id=decoded.get('role_id', 'service'),
                user_id=decoded.get('user_id', 'service'),
                session_id=decoded.get('session_id', 'service-token'),
            )

            logger.info('Valid service authentication')
            return True

        except jwt.InvalidTokenError as e:
            logger.warning(f'Invalid service token: {str(e)}')
            return False

    except Exception as e:
        logger.error(f'Error validating service authentication: {str(e)}')
        return False


async def validate_hmac_signature(
    request: Request,
    auth_secrets_repository: SQLAlchemyRepository[AuthSecrets],
) -> bool:
    """Validate HMAC signature from request headers."""
    try:
        # Get required headers
        client_key = request.headers.get(RootfloHeaders.CLIENT_KEY)
        signature = request.headers.get(RootfloHeaders.SIGNATURE)
        timestamp = request.headers.get(RootfloHeaders.TIMESTAMP)

        if not all([client_key, signature, timestamp]):
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(
                f'Missing HMAC headers: client_key={bool(client_key)}, signature={bool(signature)}, timestamp={bool(timestamp)} [Request ID: {request_id}]'
            )
            return False

        # Validate timestamp to prevent replay attacks (5 minute window)
        try:
            request_timestamp = int(timestamp)
            current_timestamp = int(time.time())
            if abs(current_timestamp - request_timestamp) > 300:  # 5 minutes
                request_id = getattr(
                    request.state, 'request_id', get_current_request_id()
                )
                logger.warning(
                    f'Request timestamp too old or in future: {timestamp}, current: {current_timestamp} [Request ID: {request_id}]'
                )
                return False
        except ValueError:
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(
                f'Invalid timestamp format: {timestamp} [Request ID: {request_id}]'
            )
            return False

        # Find the client secret
        auth_secret = await auth_secrets_repository.find_one(client_key=client_key)
        if not auth_secret:
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(
                f'Invalid client_key: {client_key} [Request ID: {request_id}]'
            )
            return False

        body = await request.body()

        # Parse JSON body to extract nonce
        try:
            parsed_body = json.loads(body.decode('utf-8'))
            nonce = parsed_body.get('nonce')
            if not nonce:
                request_id = getattr(
                    request.state, 'request_id', get_current_request_id()
                )
                logger.warning(
                    f"Missing 'nonce' field in request body [Request ID: {request_id}]"
                )
                return False
            if len(nonce) < 32:
                request_id = getattr(
                    request.state, 'request_id', get_current_request_id()
                )
                logger.warning(
                    f"Minimum 'nonce' length required is 32 [Request ID: {request_id}]"
                )
                return False
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(f'Invalid JSON in request body [Request ID: {request_id}]')
            return False

        # Create the message to sign: nonce:timestamp
        message_to_sign = f'{nonce}:{timestamp}'

        # Generate expected signature
        expected_signature = hmac.new(
            auth_secret.client_secret.encode('utf-8'),
            message_to_sign.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        # Compare signatures
        if not hmac.compare_digest(signature, expected_signature):
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.warning(f'Invalid HMAC signature [Request ID: {request_id}]')
            return False

        request_id = getattr(request.state, 'request_id', get_current_request_id())
        logger.info(f'Valid HMAC signature [Request ID: {request_id}]')
        return True

    except Exception as e:
        request_id = getattr(request.state, 'request_id', get_current_request_id())
        logger.error(
            f'Error validating HMAC signature: {str(e)} [Request ID: {request_id}]'
        )
        return False


async def validate_mtls_auth(request: Request) -> bool:
    """Validate mTLS authentication using X-Forwarded-Client-Cert header"""
    try:
        xfcc = request.headers.get('X-Forwarded-Client-Cert')
        if not xfcc:
            return False

        # Extract SPIFFE ID from URI field
        # Format: Hash=...;URI=spiffe://...;...
        match = re.search(r'URI=(spiffe://[^;,]+)', xfcc)
        if match:
            principal = match.group(1)
            if not principal.startswith(
                'spiffe://cluster.local/ns/client-applications'
            ):
                logger.error(f'Invalid mTLS authentication. Principal: {principal}')
                return False

            # Create a service session
            request.state.session = UserSession(
                role_id=SERVICE_AUTH_ROLE_ID,
                user_id='service',
                session_id='service-token',
            )

            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.info(
                f'Valid mTLS authentication. Principal: {principal} [Request ID: {request_id}]'
            )
            return True

        request_id = getattr(request.state, 'request_id', get_current_request_id())
        logger.warning(
            f'mTLS header present but no valid URI found: {xfcc} [Request ID: {request_id}]'
        )
        return False

    except Exception as e:
        request_id = getattr(request.state, 'request_id', get_current_request_id())
        logger.error(
            f'Error validating mTLS authentication: {str(e)} [Request ID: {request_id}]'
        )
        return False


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
        token_service: TokenService = Provide[AuthContainer.token_service],
        response_formatter: ResponseFormatter = Provide[
            CommonContainer.response_formatter
        ],
        session_repository: SQLAlchemyRepository[Session] = Provide[
            UserContainer.session_repository
        ],
        cache_manager: CacheManager = Provide[UserContainer.cache_manager],
        auth_secrets_repository: SQLAlchemyRepository[AuthSecrets] = Provide[
            UserContainer.auth_secrets_repository
        ],
    ):
        try:
            if request.method == 'OPTIONS':
                return await call_next(request)

            # Check if this endpoint requires HMAC validation (skip JWT validation then)
            if request.url.path in required_hmac_apis:
                if not await validate_hmac_signature(request, auth_secrets_repository):
                    request_id = getattr(
                        request.state, 'request_id', get_current_request_id()
                    )
                    logger.error(
                        f'HMAC validation failed for {request.url.path} [Request ID: {request_id}]'
                    )
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content=response_formatter.buildErrorResponse(
                            'Invalid HMAC signature'
                        ),
                    )
            # Check for service-to-service authentication (Client-Key header + JWT)
            elif request.headers.get(RootfloHeaders.CLIENT_KEY):
                if not await validate_service_auth(
                    request, auth_secrets_repository, token_service
                ):
                    request_id = getattr(
                        request.state, 'request_id', get_current_request_id()
                    )
                    logger.error(
                        f'Service authentication failed for {request.url.path} [Request ID: {request_id}]'
                    )
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content=response_formatter.buildErrorResponse(
                            'Invalid service authentication'
                        ),
                    )
            else:  # Do the JWT validation or passthrough
                authorization = request.headers.get('Authorization')

                token = None
                if authorization and authorization.startswith('Bearer '):
                    token = authorization.split(' ')[1]

                # Skip authentication for optional APIs
                if request.url.path in optional_auth_apis:
                    return await call_next(request)

                # For non-production environments: Check passthrough authentication globally
                if environment != 'production' and request.headers.get(
                    RootfloHeaders.PASSTHROUGH
                ):
                    passthrough = request.headers.get(RootfloHeaders.PASSTHROUGH)
                    logger.info(f'PASSTHROUGH header present: {passthrough}')

                    if not passthrough_secret:
                        request_id = getattr(
                            request.state, 'request_id', get_current_request_id()
                        )
                        logger.error(
                            f'PASSTHROUGH_SECRET environment variable not set [Request ID: {request_id}]'
                        )
                        return JSONResponse(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content=response_formatter.buildErrorResponse(
                                error='passthrough is not configured'
                            ),
                        )

                    if passthrough != passthrough_secret:
                        request_id = getattr(
                            request.state, 'request_id', get_current_request_id()
                        )
                        logger.error(
                            f'Invalid passthrough secret provided [Request ID: {request_id}]'
                        )
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content=response_formatter.buildErrorResponse(
                                error='Invalid passthrough secret'
                            ),
                        )

                    # Create a service session for passthrough auth
                    request.state.session = UserSession(
                        role_id=SERVICE_AUTH_ROLE_ID,
                        user_id='passthrough',
                        session_id='passthrough-token',
                    )
                    return await call_next(request)

                # Check for mTLS authentication if no token is present
                if request.headers.get('X-Forwarded-Client-Cert'):
                    if await validate_mtls_auth(request):
                        return await call_next(request)

                if not token:
                    request_id = getattr(
                        request.state, 'request_id', get_current_request_id()
                    )
                    logger.error(
                        f'Token missing in request for {request.url.path} [Request ID: {request_id}]'
                    )
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content=response_formatter.buildErrorResponse(
                            error='Token missing in request'
                        ),
                    )
                decoded = token_service.decode_token(token)
                if 'session_id' not in decoded:
                    request_id = getattr(
                        request.state, 'request_id', get_current_request_id()
                    )
                    logger.error(
                        f'Invalid token: missing session_id [Request ID: {request_id}]'
                    )
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content=response_formatter.buildErrorResponse(
                            error='Invalid token: session not found'
                        ),
                    )

                # Try to get session from cache
                session_cache_key = get_session_cache_key(decoded['session_id'])
                cached_session = cache_manager.get_str(session_cache_key)
                if cached_session:
                    try:
                        session_data = json.loads(cached_session)
                        if session_data.get('user_id') != decoded['user_id']:
                            request_id = getattr(
                                request.state, 'request_id', get_current_request_id()
                            )
                            logger.error(
                                f'Invalid session: session does not belong to user [Request ID: {request_id}]'
                            )
                            return JSONResponse(
                                status_code=status.HTTP_401_UNAUTHORIZED,
                                content=response_formatter.buildErrorResponse(
                                    error='Invalid session'
                                ),
                            )
                    except json.JSONDecodeError:
                        request_id = getattr(
                            request.state, 'request_id', get_current_request_id()
                        )
                        logger.error(
                            f'Failed to decode cached session data, fetching from DB [Request ID: {request_id}]'
                        )
                        cached_session = None

                if not cached_session:
                    # If not in cache, fetch from DB
                    session = await session_repository.find_one(
                        id=decoded['session_id']
                    )
                    if not session:
                        request_id = getattr(
                            request.state, 'request_id', get_current_request_id()
                        )
                        logger.error(
                            f'Invalid session: session not found in database [Request ID: {request_id}]'
                        )
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content=response_formatter.buildErrorResponse(
                                error='Invalid session'
                            ),
                        )

                    # Cache the session data
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

                    if str(session.user_id) != decoded['user_id']:
                        request_id = getattr(
                            request.state, 'request_id', get_current_request_id()
                        )
                        logger.error(
                            f'Invalid session: session does not belong to user [Request ID: {request_id}]'
                        )
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

                # Check for admin-only APIs
                for admin_api_prefix in admin_apis:
                    if request.url.path.startswith(admin_api_prefix):
                        is_admin = await check_is_admin(session_obj.role_id)
                        if not is_admin:
                            logger.warning(
                                f'Non-admin user {session_obj.user_id} attempted to access admin API: {request.url.path}'
                            )
                            return JSONResponse(
                                status_code=status.HTTP_403_FORBIDDEN,
                                content=response_formatter.buildErrorResponse(
                                    'Admin access required'
                                ),
                            )
                        break

            response = await call_next(request)
            return response

        except jwt.ExpiredSignatureError as exc:
            request_id = getattr(request.state, 'request_id', get_current_request_id())
            logger.error(
                f'ExpiredSignatureError in require_auth middleware: {exc} [Request ID: {request_id}]'
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=response_formatter.buildErrorResponse(
                    error='Token has expired. Please log in again.'
                ),
            )
