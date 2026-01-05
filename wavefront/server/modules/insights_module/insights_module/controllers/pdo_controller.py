from auth_module.auth_container import AuthContainer
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from common_module.utils.serializer import serialize_values
from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.user import User
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user_role import UserRole
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
from insights_module.service.pdo_service import PdoService
from insights_module.utils.helper import fetch_data_filters
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from sqlalchemy import Result
from sqlalchemy import select
from dataclasses import dataclass

pdo_router = APIRouter()


@dataclass
class UpdateRequest:
    data: dict


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


@pdo_router.get('/{resource_name}')
@inject
async def fetch_pvo_records(
    request: Request,
    resource_name: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    resource_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[AuthContainer.resource_repository]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    cloud_service: PdoService = Depends(Provide[InsightsContainer.cloud_service]),
    filter: str | None = Query(None, alias='$filter'),
    limit: str | None = None,
    offset: str | None = None,
):
    user_id = request.state.session.user_id
    role_id = request.state.session.role_id

    if resource_name not in [
        'parsed_data_object',
        'rf_parsed_data_object',
        'rf_gold_data_object',
        'rf_gold_item_details',
    ]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid resource name: {resource_name}'
            ),
        )

    if resource_name == 'parsed_data_object':
        resource_name = 'rf_parsed_data_object'

    data_filters = []
    is_admin = await check_admin(role_id)
    if not is_admin:
        data_filters = await user_service.get_user_resources(
            user_id=user_id, scope=ResourceScope.DATA
        )

        if len(data_filters) == 0:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'Data access not set for non-admin user'
                ),
            )

        data_filters = fetch_data_filters(data_filters)
        if filter:
            filter = f"{filter} $and ({' $and '.join(data_filters)})"
        else:
            filter = f"{ ' $and '.join(data_filters)}"

    pvo_records = cloud_service.fetch_upto_limit(
        filter, limit, offset, table_name=resource_name
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'records': serialize_values(pvo_records)}
        ),
    )


@pdo_router.patch('/{resource_name}/{id}')
@inject
async def patch_pvo_records(
    request: Request,
    resource_name: str,
    id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    resource_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[AuthContainer.resource_repository]
    ),
    cloud_service: PdoService = Depends(Provide[InsightsContainer.cloud_service]),
    payload: UpdateRequest = None,
):
    user_id = request.state.session.user_id
    role_id = request.state.session.role_id

    if resource_name not in [
        'parsed_data_object',
        'rf_parsed_data_object',
        'rf_gold_data_object',
        'rf_gold_item_details',
    ]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid resource name: {resource_name}'
            ),
        )

    if resource_name == 'parsed_data_object':
        resource_name = 'rf_parsed_data_object'

    data_filters = []
    is_admin = await check_admin(role_id)
    if not is_admin:
        async with resource_repository.session() as session:
            statement = (
                select(Resource)
                .join(RoleResource, Resource.id == RoleResource.resource_id)
                .join(Role, Role.id == RoleResource.role_id)
                .join(UserRole, UserRole.role_id == Role.id)
                .join(User, UserRole.user_id == User.id)
                .where(UserRole.user_id == user_id)
                .where(User.deleted.is_(False))
                .where(Resource.scope == ResourceScope.DATA)
            )
            result: Result = await session.execute(statement)
            data_filters = result.scalars().all()

        if len(data_filters) == 0:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=response_formatter.buildErrorResponse(
                    'Data access not set for non-admin user'
                ),
            )

        data_filters = fetch_data_filters(data_filters)

    cloud_service.patch_record_by_id(
        id=id,
        table_name=resource_name,
        rls_filter=data_filters,
        update_data=payload.data,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Successfully updated the records'}
        ),
    )


@pdo_router.get('/parsed_data_object/audio')
@inject
async def fetch_audio(
    resource_url: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    cloud_service: PdoService = Depends(Provide[InsightsContainer.cloud_service]),
):
    audio_url = cloud_service.fetch_audio(resource_url)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'audio_url': audio_url}),
    )


@pdo_router.get('/parsed_data_object/transcript')
@inject
async def fetch_transcript(
    resource_url: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    cloud_service: PdoService = Depends(Provide[InsightsContainer.cloud_service]),
):
    transcripts = cloud_service.fetch_transcript(resource_url)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(transcripts),
    )
