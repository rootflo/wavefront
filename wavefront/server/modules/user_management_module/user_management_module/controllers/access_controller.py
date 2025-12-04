from typing import Optional
import uuid

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user_role import UserRole
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy import Result
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from user_management_module.models.resource import CreateRolePayload
from user_management_module.models.resource import ResourcePayload
from user_management_module.models.resource import UpdateResourcePayload
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from user_management_module.utils.user_utils import check_is_admin
from user_management_module.utils.user_utils import get_current_user

access_router = APIRouter(prefix='/v1/access')


@access_router.post('/resources')
@inject
async def create_resource(
    request: Request,
    payload: ResourcePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    resource_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[UserContainer.resource_repository]
    ),
    role_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[UserContainer.role_repository]
    ),
    role_resource_repository: SQLAlchemyRepository[RoleResource] = Depends(
        Provide[UserContainer.role_resource_repository]
    ),
    user_role_repository: SQLAlchemyRepository[UserRole] = Depends(
        Provide[UserContainer.user_role_repository]
    ),
):
    user_role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(user_role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    resources: list[Resource] = []
    roles: list[Role] = []
    role_resources: list[RoleResource] = []

    for res in payload.resources:
        # Create role for each resource
        role_id = uuid.uuid4()
        resource_id = uuid.uuid4()

        resource = Resource(
            id=resource_id,
            key=res.key,
            value=res.value,
            description=res.description,
            scope=res.scope,
            meta=res.meta,
        )

        role = Role(
            id=role_id,
            name=f'{res.key} - {res.value}',
            description=f'Resource role for {res.value}',
        )

        resources.append(resource)
        roles.append(role)

        # Create role-resource mapping
        role_resources.append(RoleResource(role_id=role_id, resource_id=resource_id))

    async with resource_repository.session() as session:
        async with session.begin():
            await resource_repository.create_all(
                resources, replace=True, session=session
            )
            await role_repository.create_all(roles, replace=True, session=session)
            await role_resource_repository.create_all(
                role_resources, replace=True, session=session
            )
            admin_users = await user_role_repository.find(
                role_id=user_role_id, session=session
            )

            permissions: list[UserRole] = []
            if admin_users and len(admin_users) > 0:
                for user in admin_users:
                    for role in roles:
                        permissions.append(
                            UserRole(user_id=user.user_id, role_id=role.id)
                        )

                await user_role_repository.create_all(
                    permissions, replace=True, session=session
                )

            await session.commit()

            resource_count = len(payload.resources)
            return JSONResponse(
                status_code=status.HTTP_201_CREATED,
                content=response_formatter.buildSuccessResponse(
                    data={'message': f'Created {resource_count} resources successfully'}
                ),
            )


@access_router.post('/roles')
@inject
async def create_role(
    request: Request,
    payload: CreateRolePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    resource_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[UserContainer.resource_repository]
    ),
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[UserContainer.role_repository]
    ),
    role_resource_repository: SQLAlchemyRepository[RoleResource] = Depends(
        Provide[UserContainer.role_resource_repository]
    ),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    resources = await resource_repository.find(id=payload.resources)

    unknown_resource_count = len(payload.resources) - len(resources)
    if len(payload.resources) != len(resources):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Found {unknown_resource_count} unknown resource(s) in the payload. Remove these resources from the payload or create these resources and then proceed'
            ),
        )

    role_id = None
    # Check if a role already exists for the given resources
    async with role_resource_repository.session() as session:
        stmt = (
            select(RoleResource.role_id)
            .where(RoleResource.resource_id.in_(payload.resources))
            .group_by(RoleResource.role_id)
            .having(
                func.count(func.distinct(RoleResource.resource_id))
                == len(payload.resources)
            )
        )
        result: Result = await session.execute(stmt)
        role_id = result.scalar()

    if role_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildSuccessResponse(
                data={
                    'message': 'Role already exists for the given resources',
                    'role_id': str(role_id),
                }
            ),
        )
    else:
        role = {
            'name': payload.name,
            'description': payload.description,
        }
        role: Role = await role_repository.create(**role)
        role_resources = [
            RoleResource(resource_id=resource, role_id=role.id)
            for resource in payload.resources
        ]
        await role_resource_repository.create_all(role_resources)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response_formatter.buildSuccessResponse(
                data={
                    'message': 'Created role successfully',
                    'role_id': str(role.id),
                }
            ),
        )


@access_router.get('/resources')
@inject
async def get_resource(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    scopes: list[str] = Query(
        default=[ResourceScope.DASHBOARD, ResourceScope.CONSOLE],
        description='The scopes of the resources to fetch',
    ),
):
    _, user_id, _ = get_current_user(request)

    resources = await user_service.get_user_resources(user_id=user_id, scopes=scopes)

    data = [res.to_dict() for res in resources]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'resources': data}),
    )


@access_router.get('/roles')
@inject
async def get_role(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    role_repository: SQLAlchemyRepository[Role] = Depends(
        Provide[UserContainer.role_repository]
    ),
    scopes: list[str] = Query(
        default=[ResourceScope.CONSOLE], description='The scopes of the roles to fetch'
    ),
    select_item: Optional[str] = None,
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )
    item_to_select = select_item.split(',') if select_item else []
    valid_columns = []
    for item in item_to_select:
        if not getattr(Role, item):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    error=f'Invalid column {item}'
                ),
            )
        valid_columns.append(getattr(Role, item))

    async with role_repository.session() as session:
        if valid_columns:
            statement = select(Role).options(selectinload(Role.resources))
            result = await session.execute(statement)
            roles = result.scalars().unique().all()
            data = []
            for role in roles:
                role_dict = {}
                for col in item_to_select:
                    if col == 'resources':
                        role_dict[col] = [
                            resource.to_dict() for resource in role.resources
                        ]
                    else:
                        role_dict[col] = str(getattr(role, col))
                data.append(role_dict)
        else:
            statement = (
                select(Role)
                .join(RoleResource, Role.id == RoleResource.role_id)
                .join(Resource, Resource.id == RoleResource.resource_id)
                .where(Resource.scope.in_(scopes))
            )
            result: Result = await session.execute(statement)
            roles = result.scalars().all()

            data = [role.to_dict() for role in roles]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(data={'roles': data}),
    )


@access_router.patch('/resources/{resource_id}')
@inject
async def patch_resources(
    request: Request,
    resource_id: str,
    payload: UpdateResourcePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter],
    ),
    resource_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[UserContainer.resource_repository]
    ),
):
    user_role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(user_role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    # Explicitly extract fields that can be updated
    update_fields = {}
    if payload.key is not None:
        update_fields['key'] = payload.key
    if payload.value is not None:
        update_fields['value'] = payload.value
    if payload.description is not None:
        update_fields['description'] = payload.description
    if payload.scope is not None:
        update_fields['scope'] = payload.scope
    if payload.meta is not None:
        update_fields['meta'] = payload.meta

    if not update_fields:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No fields provided for update'
            ),
        )
    await resource_repository.find_one_and_update({'id': resource_id}, **update_fields)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Resource updated successfully'}
        ),
    )


@access_router.delete('/resources/{resource_id}')
@inject
async def delete_resources(
    request: Request,
    resource_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter],
    ),
    resource_repository: SQLAlchemyRepository[Resource] = Depends(
        Provide[UserContainer.resource_repository]
    ),
):
    user_role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(user_role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )
    delete_resource = await resource_repository.find(id=resource_id)
    if not delete_resource:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Resource not found with the given ID.'
            ),
        )
    await resource_repository.delete_all(id=resource_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Resource deleted successfully'}
        ),
    )
