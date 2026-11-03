from authz_module import Legacy, define_action, is_allowed, requires
from auth_module.auth_container import AuthContainer
from auth_module.services.superset_service import SupersetService
from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import SUPERSET_FLAG
from common_module.feature.feature_flag import FeatureFlags
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.resource import ResourceScope
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

define_action(
    'dashboards:AccessAllDashboards',
    legacy=Legacy.ADMIN,
    description='Every dashboard, with no row-level data filters',
)


@superset_controller.get(
    '/v1/superset/authenticate',
    dependencies=[
        Depends(requires('superset:CreateGuestToken', legacy=Legacy.AUTHENTICATED))
    ],
)
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
    feature_flags: FeatureFlags = Depends(Provide[CommonContainer.feature_flags]),
    filter: str | None = Query(None, alias='$filter'),
):
    if not feature_flags.enabled(SUPERSET_FLAG):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse('Superset is not enabled'),
        )

    user_id = request.state.principal.id
    dashboards = []
    data_filters = []
    # Unrestricted callers see every dashboard and get no row filters.
    is_admin = await is_allowed(request, 'dashboards:AccessAllDashboards')

    if is_admin:
        dashboards = await user_service.get_all_resources(scope=ResourceScope.DASHBOARD)
    else:
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

        if not data_filters:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'Data access not set for user'
                ),
            )

    guest_token = await superset_service.generate_guest_token(
        user_id, dashboards, data_filters, filter
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'token': guest_token}),
    )
