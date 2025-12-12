from dependency_injector.wiring import inject, Provide
from fastapi import Depends, Request, status, APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.authenticator import Authenticator
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from plugins_module.plugins_container import PluginsContainer
from plugins_module.services.authenticator_services import (
    get_authenticator_config,
    create_authenticator_config,
    update_authenticator_config,
    delete_authenticator_config,
    get_all_authenticators,
    enable_authenticator,
    disable_authenticator,
)
from plugins_module.services.datasource_services import check_admin


authenticator_router = APIRouter()


class CreateAuthenticatorPayload(BaseModel):
    auth_name: str
    auth_type: str
    auth_desc: Optional[str] = None
    config: Dict[str, Any]


class UpdateAuthenticatorPayload(BaseModel):
    auth_desc: Optional[str] = None
    config: Dict[str, Any]


@authenticator_router.post('/v1/authenticators')
@inject
async def create_authenticator(
    request: Request,
    payload: CreateAuthenticatorPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Create a new authenticator configuration."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        authenticator = await create_authenticator_config(
            auth_name=payload.auth_name,
            auth_type=payload.auth_type,
            auth_desc=payload.auth_desc,
            config=payload.config,
            authenticator_repository=authenticator_repository,
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Authenticator created successfully',
                    'authenticator': authenticator,
                }
            ),
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to create authenticator: {str(e)}'
            ),
        )


@authenticator_router.get('/v1/authenticators')
@inject
async def get_all_authenticators_endpoint(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Get all authenticator configurations."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        authenticators = await get_all_authenticators(authenticator_repository)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'authenticators': authenticators}
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to get authenticators: {str(e)}'
            ),
        )


@authenticator_router.get('/v1/authenticators/{auth_id}')
@inject
async def get_authenticator(
    request: Request,
    auth_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Get authenticator configuration by ID."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        auth_uuid = UUID(auth_id)
        authenticator = await get_authenticator_config(
            auth_uuid, authenticator_repository
        )

        if not authenticator:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'Authenticator not found: {auth_id}'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(authenticator),
        )
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Invalid authenticator ID format'
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to get authenticator: {str(e)}'
            ),
        )


@authenticator_router.put('/v1/authenticators/{auth_id}')
@inject
async def update_authenticator(
    request: Request,
    auth_id: str,
    payload: UpdateAuthenticatorPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Update authenticator configuration."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        auth_uuid = UUID(auth_id)
        authenticator = await update_authenticator_config(
            auth_id=auth_uuid,
            config=payload.config,
            auth_desc=payload.auth_desc,
            authenticator_repository=authenticator_repository,
        )

        if not authenticator:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse(
                    f'Authenticator not found: {auth_id}'
                ),
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {
                    'message': 'Authenticator updated successfully',
                    'authenticator': authenticator,
                }
            ),
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to update authenticator: {str(e)}'
            ),
        )


@authenticator_router.delete('/v1/authenticators/{auth_id}')
@inject
async def delete_authenticator(
    request: Request,
    auth_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Delete authenticator configuration."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        auth_uuid = UUID(auth_id)
        await delete_authenticator_config(auth_uuid, authenticator_repository)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'Authenticator deleted successfully'}
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to delete authenticator: {str(e)}'
            ),
        )


@authenticator_router.post('/v1/authenticators/{auth_id}/enable')
@inject
async def enable_authenticator_endpoint(
    request: Request,
    auth_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Enable an authenticator."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        auth_uuid = UUID(auth_id)
        await enable_authenticator(auth_uuid, authenticator_repository)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': f'Authenticator {auth_id} enabled successfully'}
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to enable authenticator: {str(e)}'
            ),
        )


@authenticator_router.post('/v1/authenticators/{auth_id}/disable')
@inject
async def disable_authenticator_endpoint(
    request: Request,
    auth_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    authenticator_repository: SQLAlchemyRepository[Authenticator] = Depends(
        Provide[PluginsContainer.authenticator_repository]
    ),
):
    """Disable an authenticator."""
    role_id = request.state.session.role_id

    is_admin = await check_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    try:
        auth_uuid = UUID(auth_id)
        await disable_authenticator(auth_uuid, authenticator_repository)

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': f'Authenticator {auth_id} disabled successfully'}
            ),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to disable authenticator: {str(e)}'
            ),
        )
