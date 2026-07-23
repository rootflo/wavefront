from typing import Dict, Any
from datasource.bigquery.config import BigQueryConfig
from datasource.redshift.config import RedshiftConfig
from datasource.postgres.config import PostgresConfig
from datasource.mssql.config import MSSQLConfig
from dependency_injector.wiring import inject
import asyncio
import json
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import Query
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from common_module.utils.serializer import serialize_values
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.datasource import Datasource
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from datasource import DatasourcePlugin
from datasource.types import DataSourceType, QueryResult, TableListResult
from plugins_module.services.datasource_services import (
    check_is_valid_resource,
    fetch_data_filters,
    get_datasource_config,
    validate_datasource_payload,
)
from plugins_module.utils.helper import (
    InsertRowsJsonMultiPayload,
    AddDatasourcePayload,
    UpdateDatasourcePayload,
    InsertRowsJsonPayload,
)
from plugins_module.plugins_container import PluginsContainer
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from flo_cloud.cloud_storage import CloudStorageManager
from fastapi import HTTPException
from user_management_module.utils.user_utils import check_is_admin
from user_management_module.utils.user_utils import get_current_user
from plugins_module.services.dynamic_query_service import DynamicQueryService
from db_repo_module.cache.cache_manager import CacheManager
from ..utils.helper import (
    generate_cache_key,
    generate_export_filename_hash,
    validate_yaml_query,
)
import csv
import yaml
from ..utils.helper import DynamicQueryRequest
from ..utils.helper import DynamicQueryExecuteRequest
from datetime import datetime

EXPORT_RATE_LIMIT_SECONDS = 5  # 5 seconds between exports per user

datasource_router = APIRouter()


@datasource_router.post('/v1/datasources')
@inject
async def add_datasource(
    request: Request,
    add_datasource_payload: AddDatasourcePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_repository: SQLAlchemyRepository[Datasource] = Depends(
        Provide[PluginsContainer.datasource_repository]
    ),
):
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )

    if not validate_datasource_payload(add_datasource_payload):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('Invalid datasource payload'),
        )

    config_json = json.loads(add_datasource_payload.config)

    if add_datasource_payload.type == DataSourceType.GCP_BIGQUERY:
        config = BigQueryConfig(**config_json)
    elif add_datasource_payload.type == DataSourceType.AWS_REDSHIFT:
        config = RedshiftConfig(**config_json)
    elif add_datasource_payload.type == DataSourceType.POSTGRES:
        config = PostgresConfig(**config_json)
    elif add_datasource_payload.type == DataSourceType.MSSQL:
        config = MSSQLConfig(**config_json)
    else:
        raise ValueError(f'Invalid datasource type: {add_datasource_payload.type}')

    datasource_plugin = DatasourcePlugin(add_datasource_payload.type, config)

    connection_result = await datasource_plugin.test_connection()

    if not connection_result:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                'Data source connection failed.'
            ),
        )

    datasource: Datasource = await datasource_repository.create(
        name=add_datasource_payload.name,
        type=add_datasource_payload.type,
        config=config_json,
        description=add_datasource_payload.description,
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Datasource created successfully',
                'datasource_id': str(datasource.id),
            }
        ),
    )


@datasource_router.patch('/v1/datasources/{datasource_id}')
@inject
async def update_datasource(
    request: Request,
    datasource_id: str,
    update_datasource_payload: UpdateDatasourcePayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_repository: SQLAlchemyRepository[Datasource] = Depends(
        Provide[PluginsContainer.datasource_repository]
    ),
):
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )

    # Check if datasource exists
    existing_datasource = await datasource_repository.find_one(id=datasource_id)
    if not existing_datasource:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )

    # Prepare update data
    update_data = {}

    if update_datasource_payload.name is not None:
        update_data['name'] = update_datasource_payload.name

    if update_datasource_payload.description is not None:
        update_data['description'] = update_datasource_payload.description

    # Handle type and config updates (they go together)
    if (
        update_datasource_payload.type is not None
        or update_datasource_payload.config is not None
    ):
        # Use provided type or keep existing type
        datasource_type = update_datasource_payload.type or existing_datasource.type

        if update_datasource_payload.config is not None:
            payload_config = json.loads(update_datasource_payload.config)

            if datasource_type == DataSourceType.GCP_BIGQUERY:
                config = BigQueryConfig(**payload_config)
            elif datasource_type == DataSourceType.AWS_REDSHIFT:
                config = RedshiftConfig(**payload_config)
            elif datasource_type == DataSourceType.POSTGRES:
                config = PostgresConfig(**payload_config)
            elif datasource_type == DataSourceType.MSSQL:
                config = MSSQLConfig(**payload_config)
            else:
                raise ValueError(f'Invalid datasource type: {datasource_type}')

            # Test connection with new config
            datasource_plugin = DatasourcePlugin(datasource_type, config)
            connection_result = await datasource_plugin.test_connection()

            if not connection_result:
                return JSONResponse(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    content=response_formatter.buildErrorResponse(
                        'Data source connection failed.'
                    ),
                )

            update_data['config'] = payload_config

        if update_datasource_payload.type is not None:
            update_data['type'] = datasource_type

    if not update_data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'No valid fields provided for update'
            ),
        )

    # Update datasource
    updated_datasource = await datasource_repository.find_one_and_update(
        filters={'id': datasource_id}, refresh=True, **update_data
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Datasource updated successfully',
                'datasource_id': str(updated_datasource.id),
                'datasource': Datasource.to_dict(updated_datasource),
            }
        ),
    )


@datasource_router.delete('/v1/datasources/{datasource_id}')
@inject
async def delete_datasource(
    request: Request,
    datasource_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_repository: SQLAlchemyRepository[Datasource] = Depends(
        Provide[PluginsContainer.datasource_repository]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_is_admin(role_id)

    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )

    # Check if datasource exists
    existing_datasource = await datasource_repository.find_one(id=datasource_id)
    if not existing_datasource:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )

    # Delete datasource
    await datasource_repository.delete_all(id=datasource_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': 'Datasource deleted successfully',
                'datasource_id': str(datasource_id),
            }
        ),
    )


@datasource_router.get('/v1/datasources')
@inject
async def get_datasources(
    request: Request,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_repository: SQLAlchemyRepository[Datasource] = Depends(
        Provide[PluginsContainer.datasource_repository]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )
    datasources = await datasource_repository.find()
    datasources = [Datasource.to_dict(datasource) for datasource in datasources]
    return JSONResponse(
        content=response_formatter.buildSuccessResponse({'datasources': datasources}),
        status_code=status.HTTP_200_OK,
    )


@datasource_router.get('/v1/datasources/{datasource_id}')
@inject
async def get_datasource(
    request: Request,
    datasource_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_repository: SQLAlchemyRepository[Datasource] = Depends(
        Provide[PluginsContainer.datasource_repository]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )
    datasource = await datasource_repository.find_one(id=datasource_id)

    if not datasource:
        return JSONResponse(
            content=response_formatter.buildSuccessResponse('Datasource not found'),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return JSONResponse(
        content=response_formatter.buildSuccessResponse(Datasource.to_dict(datasource)),
        status_code=status.HTTP_200_OK,
    )


@datasource_router.post('/v1/datasources/{datasource_id}/test-connection')
@inject
async def test_datasource_connection(
    request: Request,
    datasource_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    role_id = request.state.session.role_id
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )
    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
    connection_result = await datasource_plugin.test_connection()
    return JSONResponse(
        content=connection_result.result,
        status_code=status.HTTP_200_OK,
    )


@datasource_router.get('/v1/datasources/{datasource_id}/resources')
@inject
async def get_tables(
    request: Request,
    datasource_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    role_id = request.state.session.role_id

    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )

    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
    table_list: TableListResult = datasource_plugin.get_table_names()
    return JSONResponse(
        content=response_formatter.buildSuccessResponse(
            {'resources': table_list.result}
        ),
        status_code=status.HTTP_200_OK,
    )


@datasource_router.get('/v1/datasources/{datasource_id}/resources/{resource_id}')
@inject
async def query_datasource(
    request: Request,
    datasource_id: str,
    resource_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    query_filter: str | None = Query(None, alias='$filter'),
    projection: str | None = Query('*', alias='$select'),
    expand: str | None = Query(None, alias='$expand'),
    join: str | None = Query(None, alias='$join'),
    order_by: str | None = Query(None, alias='$orderby'),
    group_by: str | None = Query(None, alias='$groupby'),
    offset: int | None = 0,
    limit: int | None = 10,
):
    user_id = request.state.session.user_id
    role_id = request.state.session.role_id

    resource_is_valid = check_is_valid_resource(resource_id)
    if not resource_is_valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid resource name: {resource_id}'
            ),
        )

    if resource_id == 'parsed_data_object':
        resource_id = 'rf_parsed_data_object'

    rls_filters = []
    filter = query_filter
    is_admin = await check_is_admin(role_id)
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
        if query_filter:
            filter = f"{query_filter} $and ({' $and '.join(rls_filters)})"
        else:
            filter = f"{ ' $and '.join(rls_filters)}"

    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)

    join_query = None
    if join and expand:
        join_query = f'$expand={expand}&$join={join}'

    result: QueryResult = datasource_plugin.fetch_data(
        table_name=resource_id,
        projection=projection,
        filter=filter,
        join=join_query,
        offset=offset,
        limit=limit,
        order_by=order_by,
        group_by=group_by,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'records': serialize_values(result.result)}
        ),
    )


@datasource_router.post('/v1/datasources/{datasource_id}/resources/{resource_id}')
@inject
async def insert_rows_json(
    request: Request,
    datasource_id: str,
    resource_id: str,
    insert_rows_json_payload: InsertRowsJsonPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )

    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
    rows_with_created_at = [
        {**row, 'created_at': datetime.now().isoformat()}
        for row in insert_rows_json_payload.data
    ]
    await asyncio.to_thread(
        datasource_plugin.insert_rows_json, resource_id, rows_with_created_at
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': f'Inserted {len(insert_rows_json_payload.data)} rows successfully'
            }
        ),
    )


@datasource_router.post('/v1/datasources/{datasource_id}/resources')
@inject
async def insert_rows_json_multi(
    request: Request,
    datasource_id: str,
    insert_rows_json_multi_payload: InsertRowsJsonMultiPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Insert rows into multiple tables of one datasource atomically.

    All tables are written in a single transaction (all-or-nothing). Currently
    only Postgres supports this; other datasource types return 501.
    """
    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )

    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)

    prepared = []
    for insert in insert_rows_json_multi_payload.inserts:
        rows = [insert.data] if insert.single_row else insert.data
        rows_with_created_at = [
            {**row, 'created_at': datetime.now().isoformat()} for row in rows
        ]
        prepared.append({'table_name': insert.table_name, 'data': rows_with_created_at})

    try:
        await asyncio.to_thread(datasource_plugin.insert_rows_json_multi, prepared)
    except NotImplementedError as e:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    total_rows = sum(len(p['data']) for p in prepared)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': (
                    f'Inserted {total_rows} rows across '
                    f'{len(prepared)} table(s) successfully'
                )
            }
        ),
    )


@datasource_router.put('/v1/{datasource_id}/dynamic-queries')
@inject
async def create_dynamic_query(
    request: Request,
    datasource_id: str,
    dynamic_query: DynamicQueryRequest,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    dynamic_query_yaml_service: DynamicQueryService = Depends(
        Provide[PluginsContainer.dynamic_query_service]
    ),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        raise HTTPException(status_code=401, detail='Unauthorized')

    # validating the yaml string
    yaml_content = yaml.safe_load(dynamic_query.dynamic_query)

    if not validate_yaml_query(yaml_content):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid YAML query'
        )

    await dynamic_query_yaml_service.store_yaml_to_bucket(yaml_content, datasource_id)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Dynamic query uploaded successfully'}
        ),
    )


@datasource_router.get('/v1/{datasource_id}/dynamic-queries')
@inject
async def get_all_dynamic_query_yaml(
    request: Request,
    datasource_id: str,
    page_number: int = Query(1),
    page_size: int = Query(50),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    dynamic_query_yaml_service: DynamicQueryService = Depends(
        Provide[PluginsContainer.dynamic_query_service]
    ),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        raise HTTPException(status_code=401, detail='Unauthorized')

    result = await dynamic_query_yaml_service.retrive_dynamic_query_yaml(
        page_number, page_size
    )

    if not result['yamls']:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response_formatter.buildSuccessResponse({'yamls': []}),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(result),
    )


@datasource_router.get('/v1/{datasource_id}/dynamic-queries/{query_id}')
@inject
async def get_dynamic_query(
    request: Request,
    query_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    dynamic_query_service: DynamicQueryService = Depends(
        Provide[PluginsContainer.dynamic_query_service]
    ),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        raise HTTPException(status_code=401, detail='Unauthorized')

    yaml_query, yaml_name = await dynamic_query_service.get_dynamic_yaml_query(query_id)

    if not yaml_query:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Dynamic query not found: {query_id}'
            ),
        )
    # returning the first query
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'yaml_name': yaml_name,
                'yaml_query': yaml_query,
            }
        ),
    )


@datasource_router.post('/v1/{datasource_id}/dynamic-queries/{query_id}/execute')
@inject
async def execute_dynamic_query(
    request: Request,
    datasource_id: str,
    query_id: str,
    filter: str | None = Query(None, alias='$filter'),
    offset: int | None = 0,
    limit: int | None = 100,
    dynamic_query_params: DynamicQueryExecuteRequest = None,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    dynamic_query_yaml_service: DynamicQueryService = Depends(
        Provide[PluginsContainer.dynamic_query_service]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    cache_manager: CacheManager = Depends(Provide[PluginsContainer.cache_manager]),
    force_fetch: int = Query(0),
):
    role_id, user_id, _ = get_current_user(request)
    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )
    # fetching the yaml query based on the query_id
    yaml_query, _ = await dynamic_query_yaml_service.get_dynamic_yaml_query(query_id)

    rls_filter_str = None
    is_admin = await check_is_admin(role_id)
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
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
    # checking if the given query is already in cache
    cache_key = generate_cache_key(
        query_id,
        filter,
        rls_filter_str,
        limit,
        offset,
        dynamic_query_params.params if dynamic_query_params else None,
    )
    if not force_fetch:
        cached_result = cache_manager.get_str(cache_key)
        if cached_result:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    json.loads(cached_result)
                ),
            )
    res = await datasource_plugin.execute_dynamic_query(
        yaml_query,
        rls_filter_str,
        filter,
        offset,
        limit,
        dynamic_query_params.params if dynamic_query_params else None,
    )
    # Serialize date/datetime objects before JSON serialization
    serialized_res = serialize_values(res)
    # caching the result
    cache_manager.add(cache_key, json.dumps(serialized_res), expiry=60 * 2)

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(serialized_res),
    )


@datasource_router.post('/v1/{datasource_id}/dynamic-queries/{query_id}/export')
@inject
async def export_dynamic_query_csv(
    request: Request,
    datasource_id: str,
    query_id: str,
    filter: str | None = Query(None, alias='$filter'),
    offset: int | None = 0,
    limit: int | None = 100,
    dynamic_query_params: DynamicQueryExecuteRequest = None,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    dynamic_query_yaml_service: DynamicQueryService = Depends(
        Provide[PluginsContainer.dynamic_query_service]
    ),
    user_service: UserService = Depends(Provide[UserContainer.user_service]),
    cloud_storage_manager: CloudStorageManager = Depends(
        Provide[PluginsContainer.cloud_storage_manager]
    ),
    config: dict = Depends(Provide[PluginsContainer.config]),
    cache_manager: CacheManager = Depends(Provide[PluginsContainer.cache_manager]),
    force_fetch: int = Query(0),
):
    """Execute the dynamic query and return results as a downloadable CSV file."""
    role_id, user_id, _ = get_current_user(request)

    # Block multiple exports per user within a 2-minute window (Redis)
    export_rate_key = f'dynamic_query_export_rate:{user_id}'
    if not cache_manager.add(
        export_rate_key, '1', expiry=EXPORT_RATE_LIMIT_SECONDS, nx=True
    ):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=response_formatter.buildErrorResponse(
                f'Export rate limit: one export per user every {EXPORT_RATE_LIMIT_SECONDS // 60} minutes. Please try again later.'
            ),
        )
    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )
    yaml_query, _ = await dynamic_query_yaml_service.get_dynamic_yaml_query(query_id)
    if not yaml_query:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Dynamic query not found: {query_id}'
            ),
        )

    rls_filter_str = None
    is_admin = await check_is_admin(role_id)
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

    # Bucket and filename: hash of $filter, limit, offset, dynamic_query_params
    bucket_name = config['floware']['asset_storage_bucket']
    export_hash = generate_export_filename_hash(
        filter=filter,
        limit=limit,
        offset=offset,
        params=dynamic_query_params.params if dynamic_query_params else None,
        rls_filter_str=rls_filter_str,
    )
    filename = f'export_{query_id}_{export_hash}.csv'
    file_key = f'dynamic_query_exports/{filename}'

    # If not force_fetch, return existing file from bucket if present
    if not force_fetch:
        existing_keys, _ = cloud_storage_manager.list_files(
            bucket_name=bucket_name,
            prefix=file_key,
            page_size=1,
            page_number=1,
        )
        if existing_keys and existing_keys[0] == file_key:
            signed_url = cloud_storage_manager.generate_presigned_url(
                bucket_name=bucket_name, key=file_key, type='GET'
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {'export_url': signed_url}
                ),
            )

    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
    res: Dict[str, Any] = await datasource_plugin.execute_dynamic_query(
        yaml_query,
        rls_filter_str,
        filter,
        offset,
        limit,
        dynamic_query_params.params if dynamic_query_params else None,
    )

    if not res:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Unexpected dynamic query result format for query_id {query_id}, no results'
            ),
        )

    first_key = next(iter(res))
    if res[first_key].get('status') != 'success':
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Unexpected dynamic query result format for query_id {query_id}, no results'
            ),
        )

    serialized_res = serialize_values(res[first_key]['result'])

    # Stream rows to CSV directly in GCS/S3 to avoid building the full CSV in memory
    rows = serialized_res or []
    if not isinstance(rows, list):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=response_formatter.buildErrorResponse(
                f'Unexpected dynamic query result format for query_id {query_id}, invalid rows'
            ),
        )

    if rows:
        fieldnames = list(rows[0].keys())
        for row in rows[1:]:
            for k in row:
                if k not in fieldnames:
                    fieldnames.append(k)
    else:
        fieldnames = []

    def _cell_value(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v)
        return v if v is None or isinstance(v, str) else str(v)

    with cloud_storage_manager.open_text_writer(
        bucket_name=bucket_name, key=file_key, content_type='text/csv'
    ) as f:
        if fieldnames:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            for row in rows:
                writer.writerow({k: _cell_value(row.get(k)) for k in fieldnames})

    signed_url = cloud_storage_manager.generate_presigned_url(
        bucket_name=bucket_name, key=file_key, type='GET'
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse({'export_url': signed_url}),
    )


@datasource_router.delete('/v1/{datasource_id}/dynamic-queries/{query_id}')
@inject
async def delete_dynamic_query(
    request: Request,
    datasource_id: str,
    query_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    dynamic_query_yaml_service: DynamicQueryService = Depends(
        Provide[PluginsContainer.dynamic_query_service]
    ),
):
    role_id, _, _ = get_current_user(request)
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        raise HTTPException(status_code=401, detail='Unauthorized')
    await dynamic_query_yaml_service.delete_dynamic_query(datasource_id, query_id)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'message': 'Dynamic query deleted successfully'}
        ),
    )
