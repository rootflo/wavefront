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

build_trigger_url = 'https://cloudbuild.googleapis.com/v1/projects/aesy-330511/locations/asia-south1/triggers/new-app:webhook?key=AIzaSyA_cDcmEHojgD7SG2OI2_6DYSBMeLY8kWk&trigger=new-app&projectId=aesy-330511&secret=Buildtriggersecret'

app_router = APIRouter(prefix='/v1')


class CreateAppRequest(BaseModel):
    app_name: str
    app_url: Optional[str] = None
    app_secret: Optional[str] = None
    app_key: Optional[str] = None
    deployment_type: AppDeploymentType = AppDeploymentType.MANUAL
    type: str = 'custom'


class UpdateAppRequest(BaseModel):
    deployment_type: Optional[str] = None
    app_name: Optional[str] = None
    app_url: Optional[str] = None
    app_secret: Optional[str] = None
    app_key: Optional[str] = None


class AppResponse(BaseModel):
    id: str
    app_name: str
    app_url: str
    app_key: Optional[str] = None
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
            app_url=app.app_url,
            app_key=app.app_key,
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
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
):
    try:
        app = await app_service.get_app_by_name(app_data.app_name)
        if app:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'App with this name already exists'
                ),
            )
        if app_data.deployment_type == AppDeploymentType.MANUAL:
            if not app_data.app_secret or not app_data.app_key or not app_data.app_url:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(
                        'App secret, app key and app URL are required'
                    ),
                )
            app_url = app_data.app_url
        else:
            app_url = f'https://{app_data.app_name}.apps.rootflo.ai'

            data = {
                'deployment': {
                    'action': 'apply',
                },
                'app': {
                    'name': app_data.app_name,
                },
            }

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
            app_url=app_url,
            status=app_status,
            app_secret=app_data.app_secret,
            app_key=app_data.app_key,
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
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    app_service: AppService = Depends(Provide[ApplicationContainer.app_service]),
):
    # Prepare update data, filtering out None values
    update_data = {k: v for k, v in app_data.model_dump().items() if v is not None}
    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No fields to update'),
        )

    try:
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
        super_admin_emails = config['super_admin']['email'].split(',')

        user = await user_repository.find_one(id=user_id)

        if not user or user.email not in super_admin_emails:
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

    response = requests.get(url + '/v1/health')

    if response.status_code != 200:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'status': app.status}),
        )

    hmac_response = requests.post(
        url + '/v1/developer/secrets', headers={'X-Passthrough': 'secret'}
    )
    res_json = hmac_response.json()

    if hmac_response.status_code != 201:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'status': app.status}),
        )

    await app_service.update_app(
        app_id,
        status=AppStatus.SUCCESS,
        app_key=res_json['data']['client_key'],
        app_secret=res_json['data']['client_secret'],
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'status': 'success'}),
    )
