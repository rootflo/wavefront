"""Floware's default authenticator.

Accepts, in this order -- the order the request middleware has always used:

1. passthrough secret (outside production only)
2. mTLS client certificate (SPIFFE ID), when no token or HMAC headers are sent
3. HMAC signature, on the HMAC routes, when no Authorization header is sent
4. a session token
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Sequence

import jwt
from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from authz_module import AuthenticationError, Principal, PrincipalType
from authz_module.principal import service_principal, user_principal
from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.models.session import Session
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import Provide, inject
from fastapi import status
from starlette.datastructures import Headers
from starlette.requests import Request

from user_management_module.constants.auth import SERVICE_AUTH_ROLE_ID, RootfloHeaders
from user_management_module.constants.cache import get_session_cache_key
from user_management_module.user_container import UserContainer

# Always HMAC-authenticated, on top of any routes the app configures.
BASE_HMAC_APIS = ('/floware/v1/image/analyse',)

TOKEN_EXPIRED = 'Token has expired. Please log in again.'


def _request_id(request: Request) -> str:
    return getattr(request.state, 'request_id', get_current_request_id())


def mtls_principal_prefixes(namespaces: Sequence[str]) -> tuple[str, ...]:
    """SPIFFE ID prefixes a caller in one of ``namespaces`` presents."""
    return tuple(f'spiffe://cluster.local/ns/{namespace}' for namespace in namespaces)


def matches_dynamic_route(path: str, route_pattern: str) -> bool:
    """Whether ``path`` matches a pattern with ``{param}`` placeholders.

    A placeholder matches exactly one path segment.
    """
    regex_pattern = re.sub(r'\{[^}]+\}', 'PLACEHOLDER', route_pattern)
    regex_pattern = re.escape(regex_pattern)
    regex_pattern = regex_pattern.replace('PLACEHOLDER', r'[^/]+')
    return bool(re.match(f'^{regex_pattern}$', path))


def matches_any_route(path: str, route_patterns: Sequence[str]) -> bool:
    """Check if a path matches any route in the list (supports {param} placeholders)."""
    return any(
        path == pattern if '{' not in pattern else matches_dynamic_route(path, pattern)
        for pattern in route_patterns
    )


def is_request_hmac(headers: Headers) -> bool:
    """Check whether a request is attempting HMAC authentication.

    Any of the HMAC headers counts: a caller that sends a signature but omits the
    timestamp is still attempting HMAC, and should get the HMAC error rather than
    falling through to another auth path.
    """
    return any(
        headers.get(header)
        for header in (
            RootfloHeaders.SIGNATURE,
            RootfloHeaders.CLIENT_KEY,
            RootfloHeaders.TIMESTAMP,
        )
    )


def passthrough_principal() -> Principal:
    return service_principal(
        'passthrough', role_id=SERVICE_AUTH_ROLE_ID, session_id='passthrough-token'
    )


def mtls_principal(spiffe_id: str) -> Principal:
    return service_principal(
        'service',
        role_id=SERVICE_AUTH_ROLE_ID,
        session_id='service-token',
        attributes={'spiffe_id': spiffe_id},
    )


def hmac_principal(client_key: str | None) -> Principal:
    return service_principal(
        'hmac-service',
        role_id=SERVICE_AUTH_ROLE_ID,
        session_id='hmac-token',
        attributes={'client_key': client_key} if client_key else None,
    )


def validate_passthrough_auth(
    request: Request, passthrough_secret: str | None
) -> Principal:
    """The service principal for a valid passthrough secret.

    Raises ``AuthenticationError``: 500 when no secret is configured, 401 when
    the header does not match it.
    """
    passthrough = request.headers.get(RootfloHeaders.PASSTHROUGH)
    logger.info(f'PASSTHROUGH header present: {passthrough}')

    if not passthrough_secret:
        logger.error(
            f'passthrough secret is not configured [Request ID: {_request_id(request)}]'
        )
        raise AuthenticationError(
            'passthrough is not configured', status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    if passthrough != passthrough_secret:
        logger.error(
            f'Invalid passthrough secret provided [Request ID: {_request_id(request)}]'
        )
        raise AuthenticationError('Invalid passthrough secret')

    return passthrough_principal()


def validate_mtls_auth(
    request: Request, allowed_principal_prefixes: tuple[str, ...]
) -> Principal | None:
    """The service principal for an allowed SPIFFE ID in X-Forwarded-Client-Cert."""
    try:
        xfcc = request.headers.get('X-Forwarded-Client-Cert')
        if not xfcc:
            return None

        # Extract SPIFFE ID from URI field or use the whole header if it's a SPIFFE ID
        spiffe_id = None
        match = re.search(r'URI=(spiffe://[^;,]+)', xfcc)
        if match:
            spiffe_id = match.group(1)
        elif xfcc.startswith('spiffe://'):
            spiffe_id = xfcc

        if spiffe_id:
            if not spiffe_id.startswith(allowed_principal_prefixes):
                logger.error(f'Invalid mTLS authentication. Principal: {spiffe_id}')
                return None

            logger.info(
                f'Valid mTLS authentication. Principal: {spiffe_id} '
                f'[Request ID: {_request_id(request)}]'
            )
            return mtls_principal(spiffe_id)

        logger.warning(
            f'mTLS header present but no valid principal found: {xfcc} '
            f'[Request ID: {_request_id(request)}]'
        )
        return None

    except Exception as e:
        logger.error(
            f'Error validating mTLS authentication: {str(e)} '
            f'[Request ID: {_request_id(request)}]'
        )
        return None


async def validate_hmac_signature(
    request: Request,
    auth_secrets_repository: SQLAlchemyRepository[AuthSecrets],
) -> bool:
    """Validate HMAC signature from request headers."""
    try:
        client_key = request.headers.get(RootfloHeaders.CLIENT_KEY)
        signature = request.headers.get(RootfloHeaders.SIGNATURE)
        timestamp = request.headers.get(RootfloHeaders.TIMESTAMP)

        if not all([client_key, signature, timestamp]):
            logger.warning(
                f'Missing HMAC headers: client_key={bool(client_key)}, '
                f'signature={bool(signature)}, timestamp={bool(timestamp)} '
                f'[Request ID: {_request_id(request)}]'
            )
            return False

        # Validate timestamp to prevent replay attacks (5 minute window)
        try:
            request_timestamp = int(timestamp)
            current_timestamp = int(time.time())
            if abs(current_timestamp - request_timestamp) > 300:
                logger.warning(
                    f'Request timestamp too old or in future: {timestamp}, '
                    f'current: {current_timestamp} [Request ID: {_request_id(request)}]'
                )
                return False
        except ValueError:
            logger.warning(
                f'Invalid timestamp format: {timestamp} '
                f'[Request ID: {_request_id(request)}]'
            )
            return False

        auth_secret = await auth_secrets_repository.find_one(client_key=client_key)
        if not auth_secret:
            logger.warning(
                f'Invalid client_key: {client_key} [Request ID: {_request_id(request)}]'
            )
            return False

        nonce = request.headers.get(RootfloHeaders.NONCE)
        if not nonce:
            body = await request.body()
            try:
                parsed_body = json.loads(body.decode('utf-8'))
                nonce = parsed_body.get('nonce')
                if not nonce:
                    logger.warning(
                        "Missing 'nonce' field in request body "
                        f'[Request ID: {_request_id(request)}]'
                    )
                    return False
                if len(nonce) < 32:
                    logger.warning(
                        "Minimum 'nonce' length required is 32 "
                        f'[Request ID: {_request_id(request)}]'
                    )
                    return False
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning(
                    f'Invalid JSON in request body [Request ID: {_request_id(request)}]'
                )
                return False

        message_to_sign = f'{nonce}:{timestamp}'
        expected_signature = hmac.new(
            auth_secret.client_secret.encode('utf-8'),
            message_to_sign.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_signature):
            logger.warning(
                f'Invalid HMAC signature [Request ID: {_request_id(request)}]'
            )
            return False

        logger.info(f'Valid HMAC signature [Request ID: {_request_id(request)}]')
        return True

    except Exception as e:
        logger.error(
            f'Error validating HMAC signature: {str(e)} '
            f'[Request ID: {_request_id(request)}]'
        )
        return False


@inject
async def validate_session_token(
    request: Request,
    token: str,
    token_service: TokenService = Provide[AuthContainer.token_service],
    session_repository: SQLAlchemyRepository[Session] = Provide[
        UserContainer.session_repository
    ],
    cache_manager: CacheManager = Provide[UserContainer.cache_manager],
) -> Principal:
    """The user principal for a session token whose session is still live."""
    try:
        decoded = token_service.decode_token(token)
    except jwt.ExpiredSignatureError as exc:
        logger.error(
            f'ExpiredSignatureError in require_auth middleware: {exc} '
            f'[Request ID: {_request_id(request)}]'
        )
        raise AuthenticationError(TOKEN_EXPIRED)

    if 'session_id' not in decoded:
        logger.error(
            f'Invalid token: missing session_id [Request ID: {_request_id(request)}]'
        )
        raise AuthenticationError('Invalid token: session not found')

    session_cache_key = get_session_cache_key(decoded['session_id'])
    cached_session = cache_manager.get_str(session_cache_key)
    if cached_session:
        try:
            session_data = json.loads(cached_session)
            if session_data.get('user_id') != decoded['user_id']:
                logger.error(
                    'Invalid session: session does not belong to user '
                    f'[Request ID: {_request_id(request)}]'
                )
                raise AuthenticationError('Invalid session')
        except json.JSONDecodeError:
            logger.error(
                'Failed to decode cached session data, fetching from DB '
                f'[Request ID: {_request_id(request)}]'
            )
            cached_session = None

    if not cached_session:
        session = await session_repository.find_one(id=decoded['session_id'])
        if not session:
            logger.error(
                'Invalid session: session not found in database '
                f'[Request ID: {_request_id(request)}]'
            )
            raise AuthenticationError('Invalid session')

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
            logger.error(
                'Invalid session: session does not belong to user '
                f'[Request ID: {_request_id(request)}]'
            )
            raise AuthenticationError('Invalid session')

    return Principal(
        # The token's own claim, unconverted: handlers have always received
        # whatever the token carried.
        id=decoded['user_id'],
        type=PrincipalType.USER,
        role_id=decoded['role_id'],
        session_id=decoded['session_id'],
    )


class FlowareAuthenticator:
    def __init__(
        self,
        *,
        app_env: str = 'production',
        passthrough_secret: str | None = None,
        hmac_routes: Sequence[str] = (),
        mtls_allowed_namespaces: Sequence[str],
    ):
        """
        Args:
            app_env: Passthrough auth is only honoured when this is not
                ``production``.
            passthrough_secret: Shared secret for passthrough auth (local use);
                optional.
            hmac_routes: Extra routes authenticated by HMAC signature.
            mtls_allowed_namespaces: Namespaces whose SPIFFE identities are
                accepted for mTLS auth.
        """
        self.app_env = app_env
        self.passthrough_secret = passthrough_secret
        self.required_hmac_apis = [*BASE_HMAC_APIS, *hmac_routes]
        self.mtls_allowed_principal_prefixes = mtls_principal_prefixes(
            mtls_allowed_namespaces
        )

    @inject
    async def authenticate(
        self,
        request: Request,
        auth_secrets_repository: SQLAlchemyRepository[AuthSecrets] = Provide[
            UserContainer.auth_secrets_repository
        ],
    ) -> Principal | None:
        authorization = request.headers.get('Authorization')
        token = None
        if authorization and authorization.startswith('Bearer '):
            token = authorization.split(' ')[1]

        if self.app_env != 'production' and request.headers.get(
            RootfloHeaders.PASSTHROUGH
        ):
            return validate_passthrough_auth(request, self.passthrough_secret)

        # mTLS only when the caller presents neither a token nor HMAC headers.
        mtls_header = request.headers.get('X-Forwarded-Client-Cert')
        if mtls_header and not token and not is_request_hmac(request.headers):
            logger.info(f'mTLS authentication by {mtls_header}')
            principal = validate_mtls_auth(
                request, self.mtls_allowed_principal_prefixes
            )
            if principal is None:
                logger.error(f'Invalid mTLS authentication for {request.url.path}')
                raise AuthenticationError(
                    'Invalid mTLS authentication', status.HTTP_403_FORBIDDEN
                )
            return principal

        if not authorization and matches_any_route(
            request.url.path, self.required_hmac_apis
        ):
            if not await validate_hmac_signature(request, auth_secrets_repository):
                logger.error(
                    f'HMAC validation failed for {request.url.path} '
                    f'[Request ID: {_request_id(request)}]'
                )
                raise AuthenticationError('Invalid HMAC signature')
            return hmac_principal(request.headers.get(RootfloHeaders.CLIENT_KEY))

        if not token:
            logger.error(
                f'Token missing in request for {request.url.path} '
                f'[Request ID: {_request_id(request)}]'
            )
            return None

        return await validate_session_token(request, token)


__all__ = [
    'BASE_HMAC_APIS',
    'FlowareAuthenticator',
    'is_request_hmac',
    'matches_any_route',
    'matches_dynamic_route',
    'mtls_principal_prefixes',
    'user_principal',
    'validate_hmac_signature',
    'validate_mtls_auth',
    'validate_passthrough_auth',
    'validate_session_token',
]
