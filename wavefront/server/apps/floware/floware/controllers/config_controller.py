from typing import Annotated

from fastapi import APIRouter, Request
from fastapi import UploadFile, File
from floware.di.application_container import ApplicationContainer
from common_module.response_formatter import ResponseFormatter
from common_module.common_container import CommonContainer
from fastapi.params import Depends
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from floware.services.config_service import ConfigService
from user_management_module.utils.user_utils import get_current_user, check_is_admin
from fastapi import HTTPException
from fastapi import Form
import json
from fastapi.responses import JSONResponse
from fastapi import status

config_router = APIRouter(prefix='/v1')


# this can also receive a app_config dict with key and value
@config_router.put('/settings/config/app-icon')
@inject
async def set_config(
    request: Request,
    response_formatter: Annotated[
        ResponseFormatter,
        Depends(Provide[CommonContainer.response_formatter]),
    ],
    config_service: Annotated[
        ConfigService,
        Depends(Provide[ApplicationContainer.config_service]),
    ],
    app_config: str = Form(None),
    file: UploadFile = File(None),
):
    """
    This endpoint is used to upload the logo to the cloud storage.
    The file size should be less than 1MB.
    The file type should be png, jpeg, jpg.
    The file will be saved in the config bucket with the name config_file_name.
    The config_file_name is a constant value in the config.ini file.
    """
    # checking if the user is admin
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        raise HTTPException(status_code=401, detail='Unauthorized')

    # Parse the app_config JSON string to dict
    app_config_dict = {}
    if app_config:
        try:
            app_config_dict = json.loads(app_config)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400, detail='Invalid app_config JSON format'
            )

    await config_service.store_app_config(file, app_config_dict)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Config set successfully'}
        ),
    )


@config_router.get('/settings/config')
@inject
async def get_config(
    config_service: Annotated[
        ConfigService,
        Depends(Provide[ApplicationContainer.config_service]),
    ],
    response_formatter: Annotated[
        ResponseFormatter,
        Depends(Provide[CommonContainer.response_formatter]),
    ],
):
    """
    this endpoint will return all the configuration of the application.
    such as logo, table to query, etc.
    """
    url, app_config = await config_service.get_app_config()
    if not url:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse(
                {'message': 'No config found'}
            ),
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'app_icon': url, 'app_config': app_config}
        ),
    )
