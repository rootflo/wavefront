from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from floconsole.constants.user import UserRole
from floconsole.db.models.app import App
from floconsole.db.models.user import User
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.di.application_container import ApplicationContainer
from floconsole.services.app_user_service import AppUserService
from floconsole.utils.user_utils import get_current_user


app_user_router = APIRouter(prefix='/v1')


@app_user_router.post('/apps/{app_id}/users/{user_id}')
@inject
async def grant_app_access(
    app_id: UUID,
    user_id: UUID,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_user_service: AppUserService = Depends(
        Provide[ApplicationContainer.app_user_service]
    ),
    app_repository: SQLAlchemyRepository[App] = Depends(
        Provide[ApplicationContainer.app_repository]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    """Grant user access to app (owners only)"""
    # Check authorization
    _, current_user_id, _ = get_current_user(request)
    current_user = await user_repository.find_one(id=current_user_id)

    if not current_user or current_user.role != UserRole.OWNER.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only owners can grant app access'
            ),
        )

    # Verify app exists
    app = await app_repository.find_one(id=app_id, deleted=False)
    if not app:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('App not found'),
        )

    # Verify target user exists
    target_user = await user_repository.find_one(id=user_id, deleted=False)
    if not target_user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    # Grant access
    try:
        await app_user_service.grant_app_access(user_id, app_id)
        logger.info(f'Granted user {user_id} access to app {app_id}')

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {'message': 'App access granted successfully'}
            ),
        )
    except Exception:
        logger.exception('Failed to grant app access')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to grant app access'),
        )


@app_user_router.delete('/apps/{app_id}/users/{user_id}')
@inject
async def revoke_app_access(
    app_id: UUID,
    user_id: UUID,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_user_service: AppUserService = Depends(
        Provide[ApplicationContainer.app_user_service]
    ),
    app_repository: SQLAlchemyRepository[App] = Depends(
        Provide[ApplicationContainer.app_repository]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    """Revoke user access to app (owners only)"""
    # Check authorization
    _, current_user_id, _ = get_current_user(request)
    current_user = await user_repository.find_one(id=current_user_id)

    if not current_user or current_user.role != UserRole.OWNER.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only owners can revoke app access'
            ),
        )

    # Verify app exists
    app = await app_repository.find_one(id=app_id, deleted=False)
    if not app:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('App not found'),
        )

    # Verify target user exists
    target_user = await user_repository.find_one(id=user_id, deleted=False)
    if not target_user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    # Revoke access
    try:
        await app_user_service.revoke_app_access(user_id, app_id)
        logger.info(f'Revoked user {user_id} access to app {app_id}')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'App access revoked successfully'}
            ),
        )
    except Exception:
        logger.exception('Failed to revoke app access')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Failed to revoke app access'
            ),
        )


@app_user_router.get('/apps/{app_id}/users')
@inject
async def list_app_users(
    app_id: UUID,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_user_service: AppUserService = Depends(
        Provide[ApplicationContainer.app_user_service]
    ),
    app_repository: SQLAlchemyRepository[App] = Depends(
        Provide[ApplicationContainer.app_repository]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    """List users with access to app (owners only)"""
    # Check authorization
    _, current_user_id, _ = get_current_user(request)
    current_user = await user_repository.find_one(id=current_user_id)

    if not current_user or current_user.role != UserRole.OWNER.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only owners can view app users'
            ),
        )

    # Verify app exists
    app = await app_repository.find_one(id=app_id, deleted=False)
    if not app:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('App not found'),
        )

    # Get app users
    try:
        app_users = await app_user_service.get_app_users(app_id)

        # Fetch full user details
        if app_users:
            user_ids = [app_user.user_id for app_user in app_users]
            users = await user_repository.find(id=user_ids, deleted=False)
            users_data = [user.to_dict() for user in users]
        else:
            users_data = []

        logger.info(f'Retrieved {len(users_data)} users for app {app_id}')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'users': users_data}),
        )
    except Exception:
        logger.exception('Failed to list app users')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to list app users'),
        )


@app_user_router.get('/users/{user_id}/apps')
@inject
async def list_user_apps(
    user_id: UUID,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_user_service: AppUserService = Depends(
        Provide[ApplicationContainer.app_user_service]
    ),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    """List apps accessible to user (owners only)"""
    # Check authorization
    _, current_user_id, _ = get_current_user(request)
    current_user = await user_repository.find_one(id=current_user_id)

    if not current_user or current_user.role != UserRole.OWNER.value:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only owners can view user apps'
            ),
        )
    # Verify user exists
    user = await user_repository.find_one(id=user_id, deleted=False)
    if not user:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('User not found'),
        )

    # Get user apps
    try:
        user_apps = await app_user_service.get_user_apps(user_id)
        app_ids = [str(user_app.app_id) for user_app in user_apps]

        logger.info(f'User {user_id} has access to {len(app_ids)} apps')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'app_ids': app_ids}),
        )
    except Exception:
        logger.exception('Failed to list user apps')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse('Failed to list user apps'),
        )
