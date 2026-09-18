from typing import Optional
from urllib.parse import urlencode, urlparse
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from mailer import EmailProviderError
from user_management_module.utils.user_utils import check_is_admin

from plugins_module.plugins_container import PluginsContainer
from plugins_module.services.oauth_app_service import OAuthAppNotFound
from plugins_module.services.email_connection_service import (
    ConnectionNotFound,
    EmailAppNotConfigured,
    EmailConnectionService,
    InsufficientScope,
    InvalidConnectionState,
    MailboxMismatch,
)
from plugins_module.services.email_send_service import EmailSendService
from plugins_module.utils.email_helper import (
    AuthorizeEmailConnectionPayload,
    CreateEmailConnectionPayload,
    SendEmailPayload,
    decode_email_oauth_state,
    is_allowed_client_redirect,
)

email_connection_router = APIRouter(prefix='/v1/email-connections', tags=['email'])


def _client_redirect(
    url: Optional[str],
    web_url: str,
    *,
    error: Optional[str] = None,
) -> Optional[str]:
    """Return an absolute client URL when it matches `[web].url` origin."""
    if not url or not is_allowed_client_redirect(url, web_url):
        return None
    if error:
        separator = '&' if urlparse(url).query else '?'
        return f'{url}{separator}{urlencode({"error": error})}'
    return url


async def _forbid_non_admin(request: Request, response_formatter: ResponseFormatter):
    """None when the caller is an admin, otherwise the 403 to return.

    Email connection APIs are admin-only for now; finer RBAC comes later.
    """
    is_admin = await check_is_admin(request.state.session.role_id)
    if is_admin:
        return None
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=response_formatter.buildErrorResponse('Admin access required'),
    )


# Declared before '/{connection_id}': FastAPI matches in declaration order, so
# the dynamic route would otherwise swallow this with connection_id='oauth'.
@email_connection_router.get('/oauth/callback')
@inject
async def email_oauth_callback(
    state: str = Query(...),
    code: str = Query(...),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    config: dict = Depends(Provide[PluginsContainer.config]),
):
    """Where the provider returns after consent.

    Unauthenticated by necessity: the user arrives here from the provider's
    domain. `state` carries the connection id (and optional absolute client
    redirect URLs). Tokens are only accepted for the mailbox that connection
    expects.
    """
    web_url = ((config.get('web') or {}).get('url') or '').strip()
    try:
        connection_id, success_redirect_url, failure_redirect_url = (
            decode_email_oauth_state(state)
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    try:
        connection = await email_connection_service.complete_oauth(
            connection_id=connection_id, code=code
        )
    except ConnectionNotFound as exc:
        return _callback_failure(
            exc,
            status.HTTP_404_NOT_FOUND,
            failure_redirect_url,
            web_url,
            response_formatter,
        )
    except (MailboxMismatch, InvalidConnectionState, EmailAppNotConfigured) as exc:
        return _callback_failure(
            exc,
            status.HTTP_400_BAD_REQUEST,
            failure_redirect_url,
            web_url,
            response_formatter,
        )
    except EmailProviderError as exc:
        logger.exception('Email OAuth callback failed at the provider')
        return _callback_failure(
            exc,
            status.HTTP_502_BAD_GATEWAY,
            failure_redirect_url,
            web_url,
            response_formatter,
        )

    redirect = _client_redirect(success_redirect_url, web_url)
    if redirect:
        return RedirectResponse(url=redirect)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Mailbox connected', 'connection': connection}
        ),
    )


def _callback_failure(
    exc: Exception,
    status_code: int,
    failure_redirect_url: Optional[str],
    web_url: str,
    response_formatter: ResponseFormatter,
):
    redirect = _client_redirect(failure_redirect_url, web_url, error=str(exc))
    if redirect:
        return RedirectResponse(url=redirect)
    return JSONResponse(
        status_code=status_code,
        content=response_formatter.buildErrorResponse(str(exc)),
    )


@email_connection_router.post('', status_code=status.HTTP_201_CREATED)
@inject
async def create_email_connection(
    request: Request,
    payload: CreateEmailConnectionPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
    config: dict = Depends(Provide[PluginsContainer.config]),
):
    """Start connecting a mailbox: returns the consent URL to send the user to."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    web_url = ((config.get('web') or {}).get('url') or '').strip()
    for field_name, redirect_url in (
        ('success_redirect_url', payload.success_redirect_url),
        ('failure_redirect_url', payload.failure_redirect_url),
    ):
        if redirect_url and not is_allowed_client_redirect(redirect_url, web_url):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'{field_name} must match the configured web URL origin'
                ),
            )

    try:
        connection, consent_url = await email_connection_service.create_connection(
            name=payload.name,
            provider=payload.provider,
            capabilities=payload.capabilities,
            oauth_app_id=UUID(payload.oauth_app_id),
            created_by=request.state.session.user_id,
            success_redirect_url=payload.success_redirect_url,
            failure_redirect_url=payload.failure_redirect_url,
        )
    except EmailAppNotConfigured as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Email connection created; authorize it to finish',
                'connection': connection,
                'authorization_url': consent_url,
            }
        ),
    )


@email_connection_router.get('')
@inject
async def list_email_connections(
    request: Request,
    provider: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias='status'),
    limit: int = Query(default=100, ge=1, le=500),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
):
    """List connections. Admin-only until email RBAC is configured."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        connections = await email_connection_service.list_connections(
            provider=provider, status=status_filter, limit=limit
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'connections': connections}
            ),
        )
    except Exception:
        logger.exception('Failed to list email connections')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Failed to list email connections'
            ),
        )


@email_connection_router.get('/{connection_id}')
@inject
async def get_email_connection(
    request: Request,
    connection_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
):
    """Fetch one connection. Admin-only until email RBAC is configured."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        connection = await email_connection_service.get_connection(connection_id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'connection': connection}),
        )
    except ConnectionNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )


@email_connection_router.post('/{connection_id}/authorize')
@inject
async def authorize_email_connection(
    request: Request,
    connection_id: UUID,
    payload: AuthorizeEmailConnectionPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
    config: dict = Depends(Provide[PluginsContainer.config]),
):
    """Consent URL for a first grant or to add capabilities to an existing one.

    Already-granted capabilities are included automatically, so upgrading never
    costs the connection its existing permissions.
    """
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    web_url = ((config.get('web') or {}).get('url') or '').strip()
    for field_name, redirect_url in (
        ('success_redirect_url', payload.success_redirect_url),
        ('failure_redirect_url', payload.failure_redirect_url),
    ):
        if redirect_url and not is_allowed_client_redirect(redirect_url, web_url):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'{field_name} must match the configured web URL origin'
                ),
            )

    try:
        url = await email_connection_service.build_authorize_url(
            connection_id,
            payload.capabilities,
            success_redirect_url=payload.success_redirect_url,
            failure_redirect_url=payload.failure_redirect_url,
        )
    except ConnectionNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except (EmailAppNotConfigured, OAuthAppNotFound) as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'authorization_url': url}),
    )


@email_connection_router.post('/{connection_id}/verify')
@inject
async def verify_email_connection(
    request: Request,
    connection_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
):
    """Refresh if needed and confirm the provider still accepts the tokens.

    Updates `status` / `last_error` so admins can tell a revoked grant from a
    still-working connection without waiting for the next send or trigger.
    """
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        connection = await email_connection_service.verify_connection(connection_id)
    except ConnectionNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except MailboxMismatch as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except (InvalidConnectionState, EmailAppNotConfigured, OAuthAppNotFound) as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except EmailProviderError as exc:
        logger.exception(f'Provider rejected verify for connection {connection_id}')
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Email connection verified',
                'connection': connection,
            }
        ),
    )


@email_connection_router.post('/{connection_id}/set-primary')
@inject
async def set_primary_email_connection(
    request: Request,
    connection_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
):
    """Make this connection the platform sender used by password reset mail and
    by any job that does not name its own sender."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        connection = await email_connection_service.set_primary(connection_id)
    except ConnectionNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except InsufficientScope as exc:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except (InvalidConnectionState, EmailAppNotConfigured) as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Primary email connection updated',
                'connection': connection,
            }
        ),
    )


@email_connection_router.post('/{connection_id}/send')
@inject
async def send_from_email_connection(
    request: Request,
    connection_id: UUID,
    payload: SendEmailPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_send_service: EmailSendService = Depends(
        Provide[PluginsContainer.email_send_service]
    ),
):
    """Send one message from this connection.

    Admin-only until email RBAC is configured. The agent email tool posts here
    so it never handles tokens itself.
    """
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        await email_send_service.send(
            subject=payload.subject,
            body_html=payload.body,
            recipients=payload.to,
            connection_id=connection_id,
            sender_display_name=payload.sender_display_name,
        )
    except ConnectionNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except InsufficientScope as exc:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except (InvalidConnectionState, EmailAppNotConfigured, ValueError) as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(exc)),
        )
    except EmailProviderError as exc:
        logger.exception(f'Provider rejected send from connection {connection_id}')
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'message': 'Email sent'}),
    )


@email_connection_router.delete('/{connection_id}')
@inject
async def delete_email_connection(
    request: Request,
    connection_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    email_connection_service: EmailConnectionService = Depends(
        Provide[PluginsContainer.email_connection_service]
    ),
):
    """Delete a connection and discard its tokens."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        await email_connection_service.delete_connection(connection_id)
    except ConnectionNotFound as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(exc)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Email connection deleted'}
        ),
    )
