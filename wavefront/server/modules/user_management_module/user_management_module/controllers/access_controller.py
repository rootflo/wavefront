from typing import Optional
import uuid

from db_repo_module.models.resource import Resource
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from dependency_injector.wiring import inject
from fastapi import APIRouter
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy import or_
from sqlalchemy import Result
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from user_management_module.dependencies.injection import (
    ResourceRepositoryDep,
    ResponseFormatterDep,
    RoleRepositoryDep,
    RoleResourceRepositoryDep,
    UserServiceDep,
)
from user_management_module.models.resource import CreateRolePayload
from user_management_module.models.resource import ResourcePayload
from user_management_module.models.resource import UpdateResourcePayload
from user_management_module.models.resource import UpdateRolePayload
from user_management_module.utils.user_utils import check_is_admin
from user_management_module.utils.user_utils import get_current_user

access_router = APIRouter(prefix='/v1/access')


@access_router.post('/resources')
@inject
async def create_resource(
    request: Request,
    payload: ResourcePayload,
    response_formatter: ResponseFormatterDep,
    resource_repository: ResourceRepositoryDep,
    role_repository: RoleRepositoryDep,
    role_resource_repository: RoleResourceRepositoryDep,
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
    response_formatter: ResponseFormatterDep,
    resource_repository: ResourceRepositoryDep,
    role_repository: RoleRepositoryDep,
    role_resource_repository: RoleResourceRepositoryDep,
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
    response_formatter: ResponseFormatterDep,
    user_service: UserServiceDep,
    scopes: Optional[list[str]] = Query(
        default=None,
        description='Scopes of the resources to fetch (all scopes when omitted)',
    ),
    search: Optional[str] = Query(
        None, description='Search by key, value or description'
    ),
    limit: Optional[int] = Query(
        None, description='Maximum number of resources to return (all when omitted)'
    ),
    offset: int = Query(0, description='Number of resources to skip'),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    if not scopes:
        parsed_scopes = [
            ResourceScope.CONSOLE,
            ResourceScope.DASHBOARD,
            ResourceScope.ROUTE,
            ResourceScope.DATA,
        ]
    else:
        parsed_scopes = [ResourceScope(scope) for scope in scopes]

    resources = await user_service.get_all_resources(
        scopes=parsed_scopes, search=search, offset=offset, limit=limit
    )
    total = await user_service.count_all_resources(scopes=parsed_scopes, search=search)

    data = [res.to_dict() for res in resources]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'resources': data, 'total': total}
        ),
    )


@access_router.get('/roles')
@inject
async def get_role(
    request: Request,
    response_formatter: ResponseFormatterDep,
    role_repository: RoleRepositoryDep,
    scopes: Optional[list[str]] = Query(
        default=None,
        description='Filter roles by resource scope. When omitted, all scopes are used unless composite_only is true with an empty scopes list, which returns composite roles across every scope.',
    ),
    composite_only: bool = Query(
        False,
        description=(
            'When true, only return composite roles (linked to 2+ resources). '
            'With scopes empty, returns every composite role across all scopes. '
            'With scopes set, returns only composite roles whose resource scope '
            'set exactly matches the requested scopes (all requested scopes '
            'present and no resource outside them).'
        ),
    ),
    select_item: Optional[str] = None,
    search: Optional[str] = Query(None, description='Search by name or description'),
    limit: Optional[int] = Query(
        None, description='Maximum number of roles to return (all when omitted)'
    ),
    offset: int = Query(0, description='Number of roles to skip'),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )
    item_to_select = select_item.split(',') if select_item else []
    for item in item_to_select:
        if not hasattr(Role, item):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    error=f'Invalid column {item}'
                ),
            )

    # Base join used by every role-selection subquery below. The IN-subquery
    # keeps the outer query join-free, so each role is returned exactly once.
    base_role_ids = select(RoleResource.role_id).join(
        Resource, Resource.id == RoleResource.resource_id
    )

    def _composite_exact_match(requested_scopes: list[str]):
        # A composite role (2+ resources) matches only when the set of scopes
        # across all its resources is exactly the requested set — every requested
        # scope is present and no resource falls outside it. Grouping spans all of
        # the role's resources (no scope WHERE filter) so out-of-scope resources
        # still count against the match.
        return (
            base_role_ids.group_by(RoleResource.role_id)
            .having(func.count(RoleResource.resource_id) >= 2)
            .having(
                func.count(func.distinct(Resource.scope)).filter(
                    Resource.scope.in_(requested_scopes)
                )
                == len(requested_scopes)
            )
            .having(
                func.count(RoleResource.resource_id).filter(
                    Resource.scope.not_in(requested_scopes)
                )
                == 0
            )
        )

    def _single_resource_in_scope(requested_scopes: list[str]):
        # A single-resource role matches when its only resource is in scope.
        return (
            base_role_ids.group_by(RoleResource.role_id)
            .having(func.count(RoleResource.resource_id) == 1)
            .having(
                func.count(RoleResource.resource_id).filter(
                    Resource.scope.in_(requested_scopes)
                )
                == 1
            )
        )

    if not scopes:
        if composite_only:
            # No scopes requested: every composite role, regardless of scopes.
            scoped_role_ids = base_role_ids.group_by(RoleResource.role_id).having(
                func.count(RoleResource.resource_id) >= 2
            )
        else:
            scoped_role_ids = base_role_ids.where(
                Resource.scope.in_(
                    [
                        ResourceScope.CONSOLE,
                        ResourceScope.DASHBOARD,
                        ResourceScope.ROUTE,
                        ResourceScope.DATA,
                    ]
                )
            )
        filters = [Role.id.in_(scoped_role_ids)]
    else:
        requested_scopes = list(set(scopes))
        if composite_only:
            # Only composite roles whose scope set exactly matches the request.
            filters = [Role.id.in_(_composite_exact_match(requested_scopes))]
        else:
            # Single-resource roles in scope, plus composite roles that match the
            # requested scope set exactly (so e.g. a route+data+dashboard role is
            # NOT returned under scopes=route).
            filters = [
                or_(
                    Role.id.in_(_single_resource_in_scope(requested_scopes)),
                    Role.id.in_(_composite_exact_match(requested_scopes)),
                )
            ]
    if search and search.strip():
        term = f'%{search.strip()}%'
        filters.append(or_(Role.name.ilike(term), Role.description.ilike(term)))

    async with role_repository.session() as session:
        total = (
            await session.execute(
                select(func.count()).select_from(Role).where(*filters)
            )
        ).scalar() or 0

        statement = select(Role).where(*filters)
        if 'resources' in item_to_select:
            statement = statement.options(selectinload(Role.resources))
        statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)

        roles = (await session.execute(statement)).scalars().all()

        if item_to_select:
            data = [
                {
                    col: [resource.to_dict() for resource in role.resources]
                    if col == 'resources'
                    else str(getattr(role, col))
                    for col in item_to_select
                }
                for role in roles
            ]
        else:
            data = [role.to_dict() for role in roles]

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'roles': data, 'total': total}
        ),
    )


@access_router.patch('/resources/{resource_id}')
@inject
async def patch_resources(
    request: Request,
    resource_id: str,
    payload: UpdateResourcePayload,
    response_formatter: ResponseFormatterDep,
    resource_repository: ResourceRepositoryDep,
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
    response_formatter: ResponseFormatterDep,
    resource_repository: ResourceRepositoryDep,
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


@access_router.patch('/roles/{role_id}')
@inject
async def patch_role_resources(
    request: Request,
    role_id: str,
    payload: UpdateRolePayload,
    response_formatter: ResponseFormatterDep,
    resource_repository: ResourceRepositoryDep,
    role_repository: RoleRepositoryDep,
    role_resource_repository: RoleResourceRepositoryDep,
):
    user_role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(user_role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    role = await role_repository.find_one(id=role_id)
    if not role:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Role not found with the given ID.'
            ),
        )

    # Console roles are the user's UI identity marker and are managed separately,
    # so their resource assignments must not be edited here.
    async with role_resource_repository.session() as session:
        console_stmt = (
            select(func.count())
            .select_from(RoleResource)
            .join(Resource, Resource.id == RoleResource.resource_id)
            .where(RoleResource.role_id == role_id)
            .where(Resource.scope == ResourceScope.CONSOLE)
        )
        console_resource_count = (await session.execute(console_stmt)).scalar() or 0

    if console_resource_count > 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Cannot update resources of a console role'
            ),
        )

    resources = await resource_repository.find(id=payload.resources)
    unknown_resource_count = len(payload.resources) - len(resources)
    if unknown_resource_count != 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Found {unknown_resource_count} unknown resource(s) in the payload. Remove these resources from the payload or create these resources and then proceed'
            ),
        )

    async with role_resource_repository.session() as session:
        await role_resource_repository.delete_all(role_id=role_id, session=session)
        if payload.resources:
            role_resources = [
                RoleResource(role_id=role_id, resource_id=resource_id)
                for resource_id in payload.resources
            ]
            await role_resource_repository.create_all(role_resources, session=session)
        await session.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Role resources updated successfully'}
        ),
    )


@access_router.delete('/roles/{role_id}')
@inject
async def delete_role(
    request: Request,
    role_id: str,
    response_formatter: ResponseFormatterDep,
    role_repository: RoleRepositoryDep,
    role_resource_repository: RoleResourceRepositoryDep,
):
    user_role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(user_role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=response_formatter.buildErrorResponse('Access denied'),
        )

    role = await role_repository.find_one(id=role_id)
    if not role:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                'Role not found with the given ID.'
            ),
        )

    # Console roles are the user's UI identity marker and are managed separately,
    # so they must not be deleted here.
    async with role_resource_repository.session() as session:
        console_stmt = (
            select(func.count())
            .select_from(RoleResource)
            .join(Resource, Resource.id == RoleResource.resource_id)
            .where(RoleResource.role_id == role_id)
            .where(Resource.scope == ResourceScope.CONSOLE)
        )
        console_resource_count = (await session.execute(console_stmt)).scalar() or 0

    if console_resource_count > 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Cannot delete a console role'
            ),
        )

    await role_repository.delete_all(id=role_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            data={'message': 'Role deleted successfully'}
        ),
    )
