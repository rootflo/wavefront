from auth_module.auth_container import AuthContainer
from auth_module.services.superset_service import SupersetService
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

superset_controller = APIRouter()


@inject
async def check_is_admin(
    role_id: str,
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[AuthContainer.role_repository]
    ),
) -> bool:
    role = await role_repository.find_one(id=role_id)
    if not role:
        return False

    return role.name == 'admin'


@superset_controller.get('/v1/superset/authenticate')
@inject
async def superset_authenticator(
    request: Request,
    superset_service: SupersetService = Depends(
        Provide[AuthContainer.superset_service]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    filter: str | None = Query(None, alias='$filter'),
):
    user_id = request.state.session.user_id
    role_id = request.state.session.role_id
    dashboards = []
    data_filters = []
    is_admin = await check_is_admin(role_id)

    dashboards = await user_service.get_user_resources(
        user_id=user_id, scope=ResourceScope.DASHBOARD
    )

    if not dashboards:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'User does not have access to any dashboard'
            ),
        )
    if not is_admin:
        data_filters = await user_service.get_user_resources(
            user_id=user_id, scope=ResourceScope.DATA
        )

    if not is_admin and not data_filters:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'User does not have access to any dashboard'
            ),
        )

    if data_filters and len(data_filters) < 1:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for user'
            ),
        )

    guest_token = superset_service.generate_guest_token(
        user_id, dashboards, data_filters, filter
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'token': guest_token}),
    )
