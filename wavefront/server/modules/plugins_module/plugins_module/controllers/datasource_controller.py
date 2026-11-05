import logging
from typing import Any, Dict, List, Optional
import io
import mimetypes
import posixpath
from urllib.parse import quote
from datasource.bigquery.config import BigQueryConfig
from datasource.redshift.config import RedshiftConfig
from datasource.postgres.config import PostgresConfig
from datasource.mssql.config import MSSQLConfig
from dependency_injector.wiring import inject
import asyncio
import json
from dependency_injector.wiring import Provide
from fastapi import Depends
from fastapi import File
from fastapi import Form
from fastapi import Query
from fastapi import UploadFile
from fastapi import Request
from fastapi import status
from fastapi.responses import JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRouter

from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import (
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG,
    FeatureFlags,
)
from common_module.response_formatter import ResponseFormatter
from common_module.utils.serializer import serialize_values
from db_repo_module.models.resource import ResourceScope
from db_repo_module.models.datasource import Datasource
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.cache.application_cache import (
    invalidate_datasources_cache,
)
from datasource import (
    DatasourcePlugin,
    FileStoragePlugin,
    InvalidQueryError,
    InvalidResourceError,
    build_datasource_uri,
    build_file_storage_config,
    split_datasource_uri,
    is_file_storage_type,
)
from datasource.file_storage.config import normalize_storage_path
from datasource.types import DataSourceType, QueryResult, TableListResult
from plugins_module.services.datasource_services import (
    fetch_data_filters,
    get_datasource_config,
    validate_datasource_payload,
)
from plugins_module.utils.helper import (
    CreateFolderPayload,
    InsertRowsJsonMultiPayload,
    AddDatasourcePayload,
    DeleteRowsJsonPayload,
    UpdateDatasourcePayload,
    InsertRowsJsonPayload,
    UpdateRowsJsonPayload,
    UpdateRowsJsonMultiPayload,
)
from flo_cloud.postgres import NoRowsMatchedError
from plugins_module.services.datasource_audit_service import (
    AuditEntry,
    DatasourceAuditService,
)
from plugins_module.plugins_container import PluginsContainer
from user_management_module.user_container import UserContainer
from user_management_module.services.user_service import UserService
from flo_cloud.cloud_storage import CloudStorageManager
from flo_cloud.exceptions import CloudStorageFileNotFoundError
from fastapi import HTTPException
from user_management_module.utils.user_utils import check_is_admin
from user_management_module.utils.user_utils import get_current_user
from plugins_module.services.dynamic_query_service import DynamicQueryService
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


def _build_datasource_config(datasource_type: str, config_json: dict):
    """Config object for ``datasource_type``; ValueError if it is unsupported."""
    if is_file_storage_type(datasource_type):
        return build_file_storage_config(datasource_type, config_json)
    if datasource_type == DataSourceType.GCP_BIGQUERY:
        return BigQueryConfig(**config_json)
    if datasource_type == DataSourceType.AWS_REDSHIFT:
        return RedshiftConfig(**config_json)
    if datasource_type == DataSourceType.POSTGRES:
        return PostgresConfig(**config_json)
    if datasource_type == DataSourceType.MSSQL:
        return MSSQLConfig(**config_json)
    raise ValueError(f'Invalid datasource type: {datasource_type}')


async def _test_datasource_connection(datasource_type: str, config) -> bool:
    if is_file_storage_type(datasource_type):
        return await FileStoragePlugin(config).test_connection()
    result = await DatasourcePlugin(datasource_type, config).test_connection()
    return result.result


def _file_storage_unsupported(response_formatter: ResponseFormatter) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=response_formatter.buildErrorResponse(
            'This operation is not supported for file storage datasources'
        ),
    )


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
    cache_manager: CacheManager = Depends(Provide[PluginsContainer.cache_manager]),
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

    try:
        config = _build_datasource_config(add_datasource_payload.type, config_json)
    except (ValueError, TypeError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    connection_result = await _test_datasource_connection(
        add_datasource_payload.type, config
    )

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
    invalidate_datasources_cache(cache_manager)

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
    cache_manager: CacheManager = Depends(Provide[PluginsContainer.cache_manager]),
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

    # A file storage datasource's type and config are fixed: a new bucket or
    # provider would orphan every path already handed out. Unchanged values
    # (the edit dialog resends them) are ignored.
    if is_file_storage_type(existing_datasource.type) or is_file_storage_type(
        update_datasource_payload.type
    ):
        changes_type = (
            update_datasource_payload.type is not None
            and update_datasource_payload.type != existing_datasource.type
        )
        changes_config = update_datasource_payload.config is not None and json.loads(
            update_datasource_payload.config
        ) != (existing_datasource.config or {})
        if changes_type or changes_config:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'Only the name and description of a file storage datasource '
                    'can be changed; delete it and create a new one instead'
                ),
            )
        update_datasource_payload = update_datasource_payload.model_copy(
            update={'type': None, 'config': None}
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

            try:
                config = _build_datasource_config(datasource_type, payload_config)
            except (ValueError, TypeError) as e:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=response_formatter.buildErrorResponse(str(e)),
                )

            # Test connection with new config
            connection_result = await _test_datasource_connection(
                datasource_type, config
            )

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
    invalidate_datasources_cache(cache_manager)

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
    cache_manager: CacheManager = Depends(Provide[PluginsContainer.cache_manager]),
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
    invalidate_datasources_cache(cache_manager)

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
    connection_result = await _test_datasource_connection(
        datasource_type, datasource_config
    )
    return JSONResponse(
        content=connection_result,
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
    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
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
    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)

    join_query = None
    if join and expand:
        join_query = f'$expand={expand}&$join={join}'

    try:
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
    except (InvalidResourceError, InvalidQueryError) as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'records': serialize_values(result.result)}
        ),
    )


def _insert_entries(prepared: list[dict], payload_inserts) -> list[AuditEntry]:
    """One audit entry per table for the multi-table insert path.

    Inserts have no RETURNING: what gets recorded is what was submitted, which
    is what `snapshot: 'submitted'` says. Server defaults, triggers and
    generated columns are therefore not reflected.

    ``meta.multi_table`` records that the call spanned several tables, not that
    it was transactional — every mutation through these endpoints is, since even
    a single-table multi-row insert is one executemany in one transaction.
    """
    return [
        AuditEntry(
            table_name=spec['table_name'],
            snapshot='submitted',
            rows=spec['data'],
            rows_affected=len(spec['data']),
            meta={
                'multi_table': True,
                'batch_index': index,
                'batch_size': len(prepared),
                'single_row': payload_inserts[index].single_row,
            },
        )
        for index, spec in enumerate(prepared)
    ]


def _update_entries(results, payload) -> list[AuditEntry]:
    """One audit entry per table for the multi-table update path.

    ``results`` and ``payload.updates`` are index-aligned: the client builds one
    RowMutationResult per entry, in order.
    """
    return [
        AuditEntry(
            table_name=result.table_name,
            snapshot='after',
            rows=result.rows,
            before_rows=result.before_rows,
            key_columns=result.key_columns,
            rows_affected=result.rows_affected,
            truncated=result.truncated,
            filter=update.filter,
            filter_params=result.filter_params,
            meta={
                'multi_table': True,
                'require_all_matched': payload.require_all_matched,
                'batch_index': index,
                'batch_size': len(results),
                'patch': update.data,
            },
        )
        for index, (result, update) in enumerate(zip(results, payload.updates))
    ]


@datasource_router.post('/v1/datasources/{datasource_id}/resources/insert')
@inject
async def insert_rows_json_multi(
    request: Request,
    datasource_id: str,
    insert_rows_json_multi_payload: InsertRowsJsonMultiPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
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

    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
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
    except InvalidResourceError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='insert',
        entries=_insert_entries(prepared, insert_rows_json_multi_payload.inserts),
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
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
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

    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)
    rows_with_created_at = [
        {**row, 'created_at': datetime.now().isoformat()}
        for row in insert_rows_json_payload.data
    ]
    try:
        await asyncio.to_thread(
            datasource_plugin.insert_rows_json, resource_id, rows_with_created_at
        )
    except InvalidResourceError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    # The only mutation path that runs for every datasource type, not just
    # Postgres — it needs no RETURNING, because the rows submitted are already
    # in hand.
    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='insert',
        entries=[
            AuditEntry(
                table_name=resource_id,
                snapshot='submitted',
                rows=rows_with_created_at,
                rows_affected=len(rows_with_created_at),
                meta={'multi_table': False},
            )
        ],
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': f'Inserted {len(insert_rows_json_payload.data)} rows successfully'
            }
        ),
    )


# Registered BEFORE the single-table PATCH below: FastAPI matches in declaration
# order, so the '{resource_id}' route would otherwise swallow this one with
# resource_id='update'. (Same reason '/resources/insert' precedes its own
# catch-all. It does mean a table literally named 'update' cannot be reached by
# the single-table endpoint — as is already true for one named 'insert'.)
@datasource_router.patch('/v1/datasources/{datasource_id}/resources/update')
@inject
async def update_rows_json_multi(
    request: Request,
    datasource_id: str,
    update_rows_json_multi_payload: UpdateRowsJsonMultiPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
    ),
):
    """Update rows across multiple tables of one datasource atomically.

    All tables are written in a single transaction (all-or-nothing). By default a
    filter that matches nothing aborts the whole update: the premise here is that
    these rows move together, so a target that does not exist means the premise is
    false. Pass `require_all_matched: false` for best-effort semantics.

    Currently only Postgres supports this; other datasource types return 501.
    """
    is_admin = await check_is_admin(request.state.session.role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only admin users can update rows'
            ),
        )

    if not update_rows_json_multi_payload.updates:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No updates provided'),
        )

    for update in update_rows_json_multi_payload.updates:
        if not update.filter.strip():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    'A non-empty filter is required to update rows, missing for '
                    f'table {update.table_name}'
                ),
            )
        if not update.data:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'No columns to update for table {update.table_name}'
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

    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)

    try:
        results = await asyncio.to_thread(
            datasource_plugin.update_rows_json_multi,
            [update.model_dump() for update in update_rows_json_multi_payload.updates],
            update_rows_json_multi_payload.require_all_matched,
            capture=True,
            capture_limit=datasource_audit_service.capture_limit,
        )
    except NotImplementedError as e:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except NoRowsMatchedError as e:
        # 409, not 404: the request was well formed and every statement was valid,
        # but the database is not in the state the caller expected. Nothing was
        # written — the transaction was rolled back before this was raised.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='update',
        entries=_update_entries(results, update_rows_json_multi_payload),
    )

    total_rows = sum(result.rows_affected for result in results)
    # Rebuilt field by field rather than serialized wholesale: the client
    # contract is exactly {table_name, updated_rows}, and handing the richer
    # result object straight to JSONResponse is how captured row data would end
    # up in an API response.
    client_results = [
        {'table_name': result.table_name, 'updated_rows': result.rows_affected}
        for result in results
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': (
                    f'Updated {total_rows} rows across '
                    f'{len(results)} table(s) successfully'
                ),
                'updated_rows': total_rows,
                'results': client_results,
            }
        ),
    )


@datasource_router.patch('/v1/datasources/{datasource_id}/resources/{resource_id}')
@inject
async def update_rows_json(
    request: Request,
    datasource_id: str,
    resource_id: str,
    update_rows_json_payload: UpdateRowsJsonPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
    ),
):
    """Update the rows of one table matching an OData filter.

    The filter travels in the body rather than as a `$filter` query param (the
    shape the read endpoint uses, because a GET has no body): a mutation's
    predicate should not end up in access logs or a Referer header, and putting
    it in the body spares the caller from URL-encoding the quotes and spaces in
    `id eq '...'`.

    Currently only Postgres supports this; other datasource types return 501.
    """
    is_admin = await check_is_admin(request.state.session.role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only admin users can update rows'
            ),
        )

    if not update_rows_json_payload.filter.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'A non-empty filter is required to update rows'
            ),
        )

    if not update_rows_json_payload.data:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse('No columns to update'),
        )

    datasource_type, datasource_config = await get_datasource_config(datasource_id)
    if not datasource_config:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Datasource not found: {datasource_id}'
            ),
        )

    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)

    try:
        result = await asyncio.to_thread(
            datasource_plugin.update_rows_json,
            resource_id,
            update_rows_json_payload.data,
            update_rows_json_payload.filter,
            capture=True,
            capture_limit=datasource_audit_service.capture_limit,
        )
    except NotImplementedError as e:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except ValueError as e:
        # Unparseable filter, or one that resolved to nothing.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='update',
        entries=[
            AuditEntry(
                table_name=resource_id,
                snapshot='after',
                rows=result.rows,
                before_rows=result.before_rows,
                key_columns=result.key_columns,
                rows_affected=result.rows_affected,
                truncated=result.truncated,
                filter=update_rows_json_payload.filter,
                filter_params=result.filter_params,
                meta={'multi_table': False, 'patch': update_rows_json_payload.data},
            )
        ],
    )

    updated_rows = result.rows_affected
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': f'Updated {updated_rows} rows successfully',
                'updated_rows': updated_rows,
            }
        ),
    )


@datasource_router.delete('/v1/datasources/{datasource_id}/resources/{resource_id}')
@inject
async def delete_rows_json(
    request: Request,
    datasource_id: str,
    resource_id: str,
    delete_rows_json_payload: DeleteRowsJsonPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
    ),
):
    """Delete the rows of one table matching an OData filter.

    The filter travels in the body for the same reasons as on the PATCH — a
    mutation's predicate should stay out of access logs, and the caller is spared
    URL-encoding the quotes in `id eq '...'`. A DELETE with a body is unusual but
    legal, and every alternative was worse: a `$filter` query param leaks the
    predicate, and a POST `/delete` sub-route hides a destructive operation behind
    the verb used for creation.

    Matching nothing is a success returning `deleted_rows: 0`, not a 404. The
    caller often cannot know whether the row is still there — unassigning a user
    who was already unassigned is the ordinary case — and the end state it asked
    for is the end state it got.

    Currently only Postgres supports this; other datasource types return 501.
    """
    is_admin = await check_is_admin(request.state.session.role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Only admin users can delete rows'
            ),
        )

    if not delete_rows_json_payload.filter.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'A non-empty filter is required to delete rows'
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

    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
    datasource_plugin = DatasourcePlugin(datasource_type, datasource_config)

    try:
        result = await asyncio.to_thread(
            datasource_plugin.delete_rows_json,
            resource_id,
            delete_rows_json_payload.filter,
            capture=True,
            capture_limit=datasource_audit_service.capture_limit,
        )
    except NotImplementedError as e:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except ValueError as e:
        # Unparseable filter, or one that resolved to nothing.
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    # The captured rows are the only remaining record of what was destroyed —
    # after the commit above they exist nowhere else.
    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='delete',
        entries=[
            AuditEntry(
                table_name=resource_id,
                snapshot='deleted',
                rows=result.rows,
                rows_affected=result.rows_affected,
                truncated=result.truncated,
                filter=delete_rows_json_payload.filter,
                filter_params=result.filter_params,
                meta={'multi_table': False},
            )
        ],
    )

    deleted_rows = result.rows_affected
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'message': f'Deleted {deleted_rows} rows successfully',
                'deleted_rows': deleted_rows,
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
    feature_flags: FeatureFlags = Depends(Provide[CommonContainer.feature_flags]),
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
    #
    # An unknown query_id makes the storage read raise, which without this would
    # leave the endpoint as an uncaught 500 — indistinguishable from the query
    # existing but failing. Callers cannot tell a typo from an outage, so it is
    # reported as the 404 it is, matching GET /v1/{datasource_id}/dynamic-queries/{query_id}.
    try:
        yaml_query, _ = await dynamic_query_yaml_service.get_dynamic_yaml_query(
            query_id
        )
    except CloudStorageFileNotFoundError:
        yaml_query = None

    if not yaml_query:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Dynamic query not found: {query_id}'
            ),
        )

    rls_filter_str = None
    is_admin = await check_is_admin(role_id)
    # With ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG on, non-admins are not narrowed
    # down to their DATA resources: the row-level filter stays unset, so the
    # query runs over the whole datasource exactly as it does for an admin.
    if not is_admin and not feature_flags.enabled(ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG):
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
    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
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
    bucket_name = config['storage']['application_bucket']
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
                bucket_name=bucket_name, key=file_key, operation='GET'
            )
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=response_formatter.buildSuccessResponse(
                    {'export_url': signed_url}
                ),
            )

    if is_file_storage_type(datasource_type):
        return _file_storage_unsupported(response_formatter)
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
        bucket_name=bucket_name, key=file_key, operation='GET'
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


# Types a browser would render or run if the object is opened straight from
# the bucket; they are stored as opaque bytes instead.
_ACTIVE_CONTENT_TYPES = frozenset(
    {
        'text/html',
        'application/xhtml+xml',
        'image/svg+xml',
        'text/xml',
        'application/xml',
        'text/javascript',
        'application/javascript',
    }
)


def _stored_content_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    if content_type.split(';', 1)[0].strip().lower() in _ACTIVE_CONTENT_TYPES:
        return 'application/octet-stream'
    return content_type


def _sniff_media_type(content: bytes) -> str | None:
    """Best-effort MIME from magic bytes when the object key has no extension."""
    if content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if content.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if len(content) >= 12 and content.startswith(b'RIFF') and content[8:12] == b'WEBP':
        return 'image/webp'
    return None


# Stored types that carry no real type information; fall back to filename/magic bytes.
_GENERIC_STORED_MEDIA_TYPES = frozenset(
    {'application/octet-stream', 'binary/octet-stream'}
)


def _resolve_download_media_type(
    filename: str,
    content: bytes,
    stored_content_type: str | None = None,
) -> str:
    """Prefer stored object metadata, then filename guess, then magic bytes."""
    if stored_content_type:
        mime = stored_content_type.split(';', 1)[0].strip().lower()
        if mime and mime not in _GENERIC_STORED_MEDIA_TYPES:
            return mime
    guessed = mimetypes.guess_type(filename)[0]
    if guessed:
        return guessed
    return _sniff_media_type(content) or 'application/octet-stream'


def _relative_file_path(path: str, datasource_id: str) -> str:
    """Key relative to base_path; a datasource:// path must name this datasource."""
    parsed = split_datasource_uri(path)
    if parsed is None:
        return path
    path_datasource_id, relative_path = parsed
    if path_datasource_id.lower() != datasource_id.lower():
        raise ValueError(
            f'Path belongs to datasource {path_datasource_id}, not {datasource_id}'
        )
    return relative_path


# Matches DatasourceAuditLog.table_name, which holds the file's key here.
_AUDIT_FILE_KEY_MAX_CHARS = 512


def _file_audit_entry(
    datasource_path: str,
    storage_uri: str,
    size_bytes: int,
    content_type: str | None,
    snapshot: str,
) -> AuditEntry:
    key = datasource_path.split('/', 3)[3]
    return AuditEntry(
        table_name=key[:_AUDIT_FILE_KEY_MAX_CHARS],
        snapshot=snapshot,
        rows=[
            {
                'path': datasource_path,
                'storage_uri': storage_uri,
                'size_bytes': size_bytes,
                'content_type': content_type,
            }
        ],
        rows_affected=1,
        meta={'file': True, 'key_truncated': len(key) > _AUDIT_FILE_KEY_MAX_CHARS},
    )


def _upload_target_path(path: str | None, filename: str | None) -> str:
    """``path`` if given; a trailing ``/`` (or no path) appends the file's name."""
    base_name = posixpath.basename((filename or '').replace('\\', '/'))
    if path and not path.endswith('/'):
        return path
    if not base_name:
        raise ValueError('A path or a file name is required')
    return f'{path or ""}{base_name}'


@datasource_router.get('/v1/datasources/{datasource_id}/files/list')
@inject
async def list_datasource_files(
    request: Request,
    datasource_id: str,
    prefix: str = Query(
        '',
        description='Optional key prefix relative to the datasource base path',
    ),
    page_size: int = Query(50, ge=1, le=200),
    page_number: int = Query(1, ge=1),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """List files under the datasource base path (paginated)."""
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'File listing is only supported for file storage datasources'
            ),
        )

    try:
        file_storage = FileStoragePlugin(datasource_config)
        relative_paths, has_next_page = await asyncio.to_thread(
            file_storage.list_files, prefix, page_size, page_number
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    files = [
        {
            'path': build_datasource_uri(datasource_id, relative_path),
            'relative_path': relative_path,
            'name': posixpath.basename(relative_path),
        }
        for relative_path in relative_paths
    ]
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'files': files,
                'page_number': page_number,
                'page_size': page_size,
                'has_next_page': has_next_page,
            }
        ),
    )


@datasource_router.get('/v1/datasources/{datasource_id}/files/browse')
@inject
async def browse_datasource_files(
    request: Request,
    datasource_id: str,
    prefix: str = Query(
        '',
        description='Folder to open, relative to the datasource base path; empty for the root',
    ),
    page_size: int = Query(100, ge=1, le=1000),
    page_token: Optional[str] = Query(
        None, description='next_page_token from the previous page'
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """One folder level: its sub-folders and the files directly in it, with size and dates.

    Unlike ``/files/list`` (every file under a prefix, by page number) this does not descend
    into sub-folders and pages with the provider's own token, so a folder browser can load
    one level at a time and every page costs a single list call.
    """
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'File browsing is only supported for file storage datasources'
            ),
        )

    try:
        file_storage = FileStoragePlugin(datasource_config)
        listing = await asyncio.to_thread(
            file_storage.list_folder, prefix, page_size, page_token
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'prefix': prefix,
                'folders': [
                    {
                        'name': posixpath.basename(folder.rstrip('/')),
                        'prefix': folder,
                    }
                    for folder in listing.folders
                ],
                'files': [
                    {
                        'path': build_datasource_uri(datasource_id, item.key),
                        'relative_path': item.key,
                        'name': posixpath.basename(item.key),
                        'size': item.size,
                        'content_type': item.content_type,
                        'updated_at': item.updated_at.isoformat()
                        if item.updated_at
                        else None,
                    }
                    for item in listing.files
                ],
                'next_page_token': listing.next_page_token,
            }
        ),
    )


@datasource_router.post('/v1/datasources/{datasource_id}/files')
@inject
async def upload_datasource_file(
    request: Request,
    datasource_id: str,
    file: UploadFile = File(...),
    path: str | None = Form(None),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'File upload is only supported for file storage datasources'
            ),
        )

    try:
        target_path = _upload_target_path(path, file.filename)
        datasource_path = build_datasource_uri(datasource_id, target_path)
        file_storage = FileStoragePlugin(datasource_config)
        file_content = await file.read()
        content_type = _stored_content_type(file.content_type)
        storage_uri = await asyncio.to_thread(
            file_storage.upload_file, file_content, target_path, content_type
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='upload',
        entries=[
            _file_audit_entry(
                datasource_path,
                storage_uri,
                len(file_content),
                content_type,
                snapshot='submitted',
            )
        ],
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'path': datasource_path, 'storage_uri': storage_uri}
        ),
    )


# Files per batch request; the client splits bigger uploads (a whole folder, say) into several.
MAX_BATCH_UPLOAD_FILES = 100

logger = logging.getLogger(__name__)


@datasource_router.post('/v1/datasources/{datasource_id}/files/batch')
@inject
async def upload_datasource_files_batch(
    request: Request,
    datasource_id: str,
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(
        ...,
        description='One per file, in the same order: the key relative to the base path '
        '(a trailing / keeps the file name)',
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
    ),
):
    """Upload several files in one request, e.g. a folder with its sub-folders.

    Each file stands alone: one that fails (a bad path, a storage error) is reported in its
    result and the rest still upload. The response lists a result per file, in request order.
    """
    role_id = request.state.session.role_id
    is_admin = await check_is_admin(role_id)
    if not is_admin:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse(
                'Data access not set for non-admin user'
            ),
        )

    if len(files) != len(paths):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Got {len(files)} files but {len(paths)} paths; send one path per file'
            ),
        )
    if len(files) > MAX_BATCH_UPLOAD_FILES:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'At most {MAX_BATCH_UPLOAD_FILES} files per request'
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'File upload is only supported for file storage datasources'
            ),
        )

    file_storage = FileStoragePlugin(datasource_config)
    results: List[Dict[str, Any]] = []
    audit_entries = []
    for index, (file, path) in enumerate(zip(files, paths)):
        try:
            target_path = _upload_target_path(path, file.filename)
            datasource_path = build_datasource_uri(datasource_id, target_path)
            file_content = await file.read()
            content_type = _stored_content_type(file.content_type)
            storage_uri = await asyncio.to_thread(
                file_storage.upload_file, file_content, target_path, content_type
            )
        except ValueError as e:
            results.append({'index': index, 'error': str(e)})
            continue
        except Exception:
            logger.exception('Batch upload failed for file %s', index)
            results.append({'index': index, 'error': 'Upload failed'})
            continue
        results.append(
            {'index': index, 'path': datasource_path, 'storage_uri': storage_uri}
        )
        audit_entries.append(
            _file_audit_entry(
                datasource_path,
                storage_uri,
                len(file_content),
                content_type,
                snapshot='submitted',
            )
        )

    if audit_entries:
        datasource_audit_service.record_from_request(
            request,
            datasource_id=datasource_id,
            datasource_type=datasource_type,
            operation='upload',
            entries=audit_entries,
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                'uploaded': len(audit_entries),
                'failed': len(results) - len(audit_entries),
                'results': results,
            }
        ),
    )


@datasource_router.post('/v1/datasources/{datasource_id}/files/folders')
@inject
async def create_datasource_folder(
    request: Request,
    datasource_id: str,
    payload: CreateFolderPayload,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
    ),
):
    """Create an empty folder (an empty ``<folder>/`` placeholder object, as cloud consoles do)."""
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'Folders are only supported for file storage datasources'
            ),
        )

    try:
        relative = normalize_storage_path(payload.path)
        if not relative:
            raise ValueError('path is required')
        file_storage = FileStoragePlugin(datasource_config)
        storage_uri = await asyncio.to_thread(file_storage.create_folder, relative)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )

    prefix = f'{relative}/'
    # build_datasource_uri normalizes the trailing slash away; a folder keeps it.
    datasource_path = f'{build_datasource_uri(datasource_id, relative)}/'
    # Recorded as an upload: it writes one (empty) object, like any other upload.
    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='upload',
        entries=[
            _file_audit_entry(
                datasource_path, storage_uri, 0, None, snapshot='submitted'
            )
        ],
    )

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=response_formatter.buildSuccessResponse(
            {'path': datasource_path, 'prefix': prefix, 'storage_uri': storage_uri}
        ),
    )


@datasource_router.delete('/v1/datasources/{datasource_id}/files')
@inject
async def delete_datasource_file(
    request: Request,
    datasource_id: str,
    path: str = Query(
        ...,
        description='datasource://<datasource_id>/<key> or a key relative to base_path',
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'File delete is only supported for file storage datasources'
            ),
        )

    try:
        relative_path = _relative_file_path(path, datasource_id)
        file_storage = FileStoragePlugin(datasource_config)
        storage_uri = await asyncio.to_thread(file_storage.delete_file, relative_path)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except CloudStorageFileNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(f'File not found: {path}'),
        )

    datasource_path = build_datasource_uri(datasource_id, relative_path)
    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='delete',
        entries=[
            _file_audit_entry(
                datasource_path,
                storage_uri,
                0,
                None,
                snapshot='deleted',
            )
        ],
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'path': datasource_path, 'storage_uri': storage_uri}
        ),
    )


@datasource_router.get('/v1/datasources/{datasource_id}/files')
@inject
async def download_datasource_file(
    request: Request,
    datasource_id: str,
    path: str = Query(
        ...,
        description='datasource://<datasource_id>/<key> or a key relative to base_path',
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    datasource_audit_service: DatasourceAuditService = Depends(
        Provide[PluginsContainer.datasource_audit_service]
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
    if not is_file_storage_type(datasource_type):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                'File download is only supported for file storage datasources'
            ),
        )

    try:
        relative_path = _relative_file_path(path, datasource_id)
        file_storage = FileStoragePlugin(datasource_config)
        key = file_storage.resolve_key(relative_path)
        file_content, stored_content_type = await asyncio.to_thread(
            file_storage.download_file_with_content_type, relative_path
        )
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(str(e)),
        )
    except CloudStorageFileNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(f'File not found: {path}'),
        )

    filename = posixpath.basename(key)
    media_type = _resolve_download_media_type(
        filename, file_content, stored_content_type
    )
    datasource_audit_service.record_from_request(
        request,
        datasource_id=datasource_id,
        datasource_type=datasource_type,
        operation='download',
        entries=[
            _file_audit_entry(
                build_datasource_uri(datasource_id, relative_path),
                file_storage.uri_for(key),
                len(file_content),
                media_type,
                snapshot='read',
            )
        ],
    )
    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=media_type,
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}",
            'Content-Length': str(len(file_content)),
            'X-Content-Type-Options': 'nosniff',
        },
    )
