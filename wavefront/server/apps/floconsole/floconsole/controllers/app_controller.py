import requests

from typing import Optional
from uuid import UUID

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from common_module.log.logger import logger
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter, Query
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from floconsole.services.app_service import AppService
from floconsole.di.application_container import ApplicationContainer
from floconsole.authorization.require_auth import UserSession
from floconsole.db.repositories.sql_alchemy_repository import SQLAlchemyRepository
from floconsole.db.models.user import User
from floconsole.constants.app import AppDeploymentType, AppStatus
from floconsole.constants.user import UserRole

app_router = APIRouter(prefix='/v1')


class CreateAppRequest(BaseModel):
    app_name: str
    public_url: Optional[str] = None
    private_url: Optional[str] = None
    deployment_type: AppDeploymentType = AppDeploymentType.MANUAL
    type: str = 'custom'


class UpdateAppRequest(BaseModel):
    deployment_type: Optional[str] = None
    app_name: Optional[str] = None
    public_url: Optional[str] = None
    private_url: Optional[str] = None


class AppResponse(BaseModel):
    id: str
    app_name: str
    public_url: str
    private_url: str
    status: AppStatus
    config: dict
    deployment_type: str
    type: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_model(cls, app):
        return cls(
            id=str(app.id),
            app_name=app.app_name,
            public_url=app.public_url,
            private_url=app.private_url,
            status=app.status,
            config=app.config,
            deployment_type=app.deployment_type,
            type=app.type,
            created_at=app.created_at.isoformat() if app.created_at else None,
            updated_at=app.updated_at.isoformat() if app.updated_at else None,
        )


@app_router.get('/apps')
@inject
async def get_apps(
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
):
    apps = await app_service.get_all_apps()
    apps_data = [AppResponse.from_model(app).model_dump() for app in apps]

    logger.info(f'Retrieved {len(apps)} apps successfully')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'apps': apps_data}),
    )


@app_router.post('/apps')
@inject
async def create_app(
    app_data: CreateAppRequest,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
    config: dict = Depends(Provide[ApplicationContainer.config]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    try:
        session: UserSession = request.state.session
        user_id = session.user_id

        user = await user_repository.find_one(id=user_id)

        # Only owners can create apps
        if not user or user.role != UserRole.OWNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'You are not authorized to create apps'
                ),
            )

        app = await app_service.get_app_by_name(app_data.app_name)
        if app:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'App with this name already exists'
                ),
            )
        if app_data.deployment_type == AppDeploymentType.MANUAL:
            if not app_data.public_url:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'Public URL is required for manual deployment'
                    ),
                )
            public_url = app_data.public_url
            # For manual deployment, private_url defaults to public_url if not provided
            private_url = (
                app_data.private_url if app_data.private_url else app_data.public_url
            )
        else:
            public_url = f'https://{app_data.app_name}.apps.rootflo.ai'
            # For auto deployment, private_url defaults to floware internal URL if not provided
            private_url = app_data.private_url if app_data.private_url else public_url

            data = {
                'deployment': {
                    'action': 'apply',
                },
                'app': {
                    'name': app_data.app_name,
                },
            }

            build_trigger_url = config['deployment']['build_trigger_url']
            response = requests.post(build_trigger_url, json=data)

            if response.status_code != 200:
                logger.error(f'Failed to create app: {response.json()}')
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'Failed to create app'
                    ),
                )
        app_status = (
            AppStatus.SUCCESS
            if app_data.deployment_type == AppDeploymentType.MANUAL
            else AppStatus.IN_PROGRESS
        )

        app = await app_service.create_app(
            app_name=app_data.app_name,
            public_url=public_url,
            private_url=private_url,
            status=app_status,
            deployment_type=app_data.deployment_type.value,
            type=app_data.type,
            config={},
        )

        logger.info(f'App {app_data.app_name} create successfully')

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                {
                    'app': AppResponse.from_model(app).model_dump(),
                }
            ),
        )

    except Exception as e:
        logger.error(f'Failed to create app: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to create app: {str(e)}'
            ),
        )


@app_router.get('/apps/{app_id}')
@inject
async def get_app(
    app_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
):
    app = await app_service.get_app_by_id(app_id)

    if not app:
        logger.error(f'App with ID {app_id} not found')
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('App not found'),
        )

    logger.info(f'App {app.app_name} retrieved successfully')

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'app': AppResponse.from_model(app).model_dump()}
        ),
    )


@app_router.patch('/apps/{app_id}')
@inject
async def update_app(
    app_id: UUID,
    app_data: UpdateAppRequest,
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    try:
        session: UserSession = request.state.session
        user_id = session.user_id

        user = await user_repository.find_one(id=user_id)

        # Only owners can update apps
        if not user or user.role != UserRole.OWNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'You are not authorized to update apps'
                ),
            )

        # Prepare update data, filtering out None values
        update_data = {k: v for k, v in app_data.model_dump().items() if v is not None}
        if not update_data:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse('No fields to update'),
            )

        app = await app_service.update_app(app_id, **update_data)

        if not app:
            logger.error(f'App with ID {app_id} not found for update')
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse('App not found'),
            )

        logger.info(f'App {app.app_name} updated successfully')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'app': AppResponse.from_model(app).model_dump()}
            ),
        )
    except Exception as e:
        logger.error(f'Failed to update app: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to update app: {str(e)}'
            ),
        )


@app_router.delete('/apps/{app_id}')
@inject
async def delete_app(
    app_id: UUID,
    request: Request,
    delete_deployment: bool = Query(
        True, description='Whether to delete the deployment'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
    config: dict = Depends(Provide[ApplicationContainer.config]),
    user_repository: SQLAlchemyRepository[User] = Depends(
        Provide[ApplicationContainer.user_repository]
    ),
):
    try:
        session: UserSession = request.state.session
        user_id = session.user_id

        user = await user_repository.find_one(id=user_id)

        # Only owners can delete apps
        if not user or user.role != UserRole.OWNER.value:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'You are not authorized to delete this app'
                ),
            )

        app = await app_service.get_app_by_id(app_id)

        if not app:
            logger.error(f'App with ID {app_id} not found')
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse('App not found'),
            )

        app_name = app.app_name

        if delete_deployment:
            data = {
                'deployment': {
                    'action': 'destroy',
                },
                'app': {
                    'name': app_name,
                },
            }

            build_trigger_url = config['deployment']['build_trigger_url']
            response = requests.post(build_trigger_url, json=data)

            if response.status_code != 200:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'Failed to delete app'
                    ),
                )

        deleted_app = await app_service.delete_app(app_id)

        if not deleted_app:
            logger.error(f'App with ID {app_id} not found for deletion')
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=response_formatter.buildErrorResponse('App not found'),
            )

        logger.info(f'App {app_name} deleted successfully')

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'App deleted successfully'}
            ),
        )
    except Exception as e:
        logger.error(f'Failed to delete app: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Failed to delete app: {str(e)}'
            ),
        )


@app_router.get('/apps/{app_id}/status')
@inject
async def get_app_status(
    app_id: UUID,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
):
    app = await app_service.get_app_by_id(app_id)

    if not app:
        logger.error(f'App with ID {app_id} not found')
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('App not found'),
        )

    url = f'https://{app.app_name}-floware.apps.rootflo.ai/floware'

    try:
        response = requests.get(url + '/v1/health', timeout=10)

        if response.status_code == 200:
            await app_service.update_app(app_id, status=AppStatus.SUCCESS)
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse({'status': 'success'}),
            )
        else:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse({'status': app.status}),
            )
    except requests.exceptions.RequestException as e:
        logger.warning(f'Health check failed for app {app.app_name}: {str(e)}')
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'status': app.status}),
        )
