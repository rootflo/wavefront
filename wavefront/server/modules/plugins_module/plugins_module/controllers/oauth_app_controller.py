from typing import Optional
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from flo_cloud.exceptions import KmsError
from user_management_module.utils.user_utils import check_is_admin

from plugins_module.plugins_container import PluginsContainer
from plugins_module.services.oauth_app_service import (
    OAuthAppNotFound,
    OAuthAppService,
)
from plugins_module.utils.email_helper import (
    CreateOAuthAppPayload,
    UpdateOAuthAppPayload,
)

oauth_app_router = APIRouter()


async def _forbid_non_admin(request: Request, response_formatter: ResponseFormatter):
    """None when the caller is an admin, otherwise the 403 to return.

    OAuth apps hold the platform's client credentials, so every route here is
    admin-only.
    """
    is_admin = await check_is_admin(request.state.session.role_id)
    if is_admin:
        return None
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=response_formatter.buildErrorResponse('Admin access required'),
    )


@oauth_app_router.post('/v1/oauth-apps')
@inject
async def create_oauth_app(
    request: Request,
    payload: CreateOAuthAppPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    """Register an OAuth application that features can connect through."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        app = await oauth_app_service.create_app(
            name=payload.name,
            provider=payload.provider,
            config=payload.config,
            description=payload.description,
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {'message': 'OAuth app created successfully', 'app': app}
            ),
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except KmsError:
        logger.exception('Failed to create OAuth app')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Failed to store OAuth app credentials'
            ),
        )
    except Exception:
        logger.exception('Failed to create OAuth app')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to create OAuth app'),
        )


@oauth_app_router.get('/v1/oauth-apps')
@inject
async def get_oauth_apps(
    request: Request,
    provider: Optional[str] = None,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    """List OAuth applications. Secrets and config are omitted."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        apps = await oauth_app_service.list_apps(provider=provider)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'apps': apps}),
        )
    except Exception:
        logger.exception('Failed to list OAuth apps')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to list OAuth apps'),
        )


@oauth_app_router.get('/v1/oauth-apps/{app_id}')
@inject
async def get_oauth_app(
    request: Request,
    app_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    """One OAuth app including its config, but never its client secret."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        app = await oauth_app_service.get_app(app_id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'app': app}),
        )
    except OAuthAppNotFound as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except Exception:
        logger.exception(f'Failed to get OAuth app {app_id}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to get OAuth app'),
        )


@oauth_app_router.patch('/v1/oauth-apps/{app_id}')
@inject
async def update_oauth_app(
    request: Request,
    app_id: UUID,
    payload: UpdateOAuthAppPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    """Update an OAuth app. Omitting `client_secret` keeps the stored one."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        app = await oauth_app_service.update_app(
            app_id=app_id,
            name=payload.name,
            config=payload.config,
            description=payload.description,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'OAuth app updated successfully', 'app': app}
            ),
        )
    except OAuthAppNotFound as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except KmsError:
        logger.exception(f'Failed to update OAuth app {app_id}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Failed to store OAuth app credentials'
            ),
        )
    except Exception:
        logger.exception(f'Failed to update OAuth app {app_id}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to update OAuth app'),
        )


@oauth_app_router.post('/v1/oauth-apps/{app_id}/enable')
@inject
async def enable_oauth_app(
    request: Request,
    app_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    return await _set_enabled(
        app_id, True, response_formatter, oauth_app_service, request
    )


@oauth_app_router.post('/v1/oauth-apps/{app_id}/disable')
@inject
async def disable_oauth_app(
    request: Request,
    app_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    return await _set_enabled(
        app_id, False, response_formatter, oauth_app_service, request
    )


@oauth_app_router.delete('/v1/oauth-apps/{app_id}')
@inject
async def delete_oauth_app(
    request: Request,
    app_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    oauth_app_service: OAuthAppService = Depends(
        Provide[PluginsContainer.oauth_app_service]
    ),
):
    """Soft delete an OAuth app. Connections through it stop working until
    another app is attached."""
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    try:
        await oauth_app_service.delete_app(app_id)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'OAuth app deleted successfully'}
            ),
        )
    except OAuthAppNotFound as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except Exception:
        logger.exception(f'Failed to delete OAuth app {app_id}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to delete OAuth app'),
        )


async def _set_enabled(
    app_id: UUID,
    is_enabled: bool,
    response_formatter: ResponseFormatter,
    oauth_app_service: OAuthAppService,
    request: Request,
):
    forbidden = await _forbid_non_admin(request, response_formatter)
    if forbidden:
        return forbidden

    action = 'enabled' if is_enabled else 'disabled'
    try:
        app = await oauth_app_service.set_enabled(app_id, is_enabled)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': f'OAuth app {action} successfully', 'app': app}
            ),
        )
    except OAuthAppNotFound as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except Exception:
        logger.exception(f'Failed to set OAuth app {app_id} to {action}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to update OAuth app'),
        )
