from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter
from insights_module.insights_container import InsightsContainer
from insights_module.service.dynamic_query_service import DynamicQueryService
from insights_module.utils.helper import fetch_data_filters
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService


dynamic_query_router = APIRouter()


@inject
async def check_admin(
    role_id: str,
    role_repositroy: SQLAlchemyRepository[Role] = Depends(
        Provide(AuthContainer.role_repository)
    ),
) -> bool:
    role = await role_repositroy.find_one(id=role_id)
    if not role:
        return False
    return role.name == 'admin'


@dynamic_query_router.get('/dynamic-queries/{query_id}')
@inject
async def execute_dynamic_query(
    request: Request,
    query_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    dynamic_query_service: DynamicQueryService = Depends(
        Provide[InsightsContainer.dynamic_query_service]
    ),
    filter: str | None = Query(None, alias='$filter'),
    start_date: str | None = None,
    end_date: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
    force: str | None = None,
):
    user_id = request.state.session.user_id
    role_id = request.state.session.role_id

    if not dynamic_query_service.is_valid_query(query_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Invalid query ID or query params'
            ),
        )

    rls_filter_str = None
    is_admin = await check_admin(role_id)
    if not is_admin:
        rls_filters = await user_service.get_user_resources(
            user_id=user_id, scope=ResourceScope.DATA
        )

        if len(rls_filters) == 0:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'Data access not set for non-admin user'
                ),
            )

        rls_filters = fetch_data_filters(rls_filters)
        rls_filter_str = f"{ ' $and '.join(rls_filters)}"

    all_query_params = dict(request.query_params)
    query_results = await dynamic_query_service.execute_dynamic_query(
        query_id=query_id,
        params=all_query_params,
        filter=filter,
        rls_filter_str=rls_filter_str,
        limit=limit,
        offset=offset,
        force=(force == 'true'),
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(query_results),
    )
