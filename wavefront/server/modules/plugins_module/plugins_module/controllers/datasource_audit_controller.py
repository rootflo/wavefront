"""Read API over the datasource row-mutation audit trail, admin-only by default.

Kept in its own router rather than added to ``datasource_router``: these routes
are a read-only administrative surface with nothing in common with the data
plane, and the path is deliberately a sibling of ``/v1/datasources`` rather than
a child. A child path like ``/v1/datasources/audit-logs`` would be matched by the
existing ``GET /v1/datasources/{datasource_id}`` — FastAPI resolves in
declaration order — which is the same hazard the comment above
``update_rows_json_multi`` in datasource_controller.py documents.
"""

from typing import Any, Dict, Optional, Tuple
from datetime import datetime

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Query, Request, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from common_module.common_container import CommonContainer
from common_module.feature.feature_flag import (
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG,
    is_feature_enabled,
)
from common_module.response_formatter import ResponseFormatter
from common_module.utils.serializer import serialize_values
from common_module.utils.validators import is_valid_uuid
from db_repo_module.models.datasource_audit_log import DatasourceAuditLog
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from plugins_module.plugins_container import PluginsContainer
from user_management_module.utils.user_utils import check_is_admin, get_current_user

datasource_audit_router = APIRouter()

VALID_OPERATIONS = ('insert', 'update', 'delete')

# Query params starting with this address a column of the *mutated* row, looked
# up in filter_params. The prefix is not decoration: the audited schemas are the
# caller's, so a mutated table may well have a column sharing a name with one of
# this table's own (`user_id`, `created_at`, `id`), and a bare `?user_id=` could
# mean either the actor or the targeted row's value.
FILTER_PARAM_PREFIX = 'param.'


def _extract_filter_params(request: Request) -> Dict[str, str]:
    """Pull `param.<column>=<value>` pairs out of the query string.

    Read off the raw query string because the column names are the caller's
    data, not a fixed set FastAPI could declare as arguments.
    """
    return {
        key[len(FILTER_PARAM_PREFIX) :]: value
        for key, value in request.query_params.items()
        if key.startswith(FILTER_PARAM_PREFIX) and key != FILTER_PARAM_PREFIX
    }


async def _can_read_audit_logs(request: Request) -> bool:
    """Read access to the audit trail: admin only, by default.

    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG lifts the same gate off the datasource
    read paths, and the trail is a record of those rows, so it follows them —
    a deployment that lets every authenticated user read the data has no reason
    to hide what was done to it.
    """
    if is_feature_enabled(ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG):
        return True

    role_id, _, _ = get_current_user(request)
    return await check_is_admin(role_id)


# Every column, `changes` included. It is what a listing is usually for — a UI
# rendering "what changed" would otherwise fetch the list and then one detail
# request per row.
#
# Size is bounded rather than avoided: an update stores a diff of only the
# columns it set, and the audit service caps every record at 20 rows / 256 KiB.
# Deletes are the heavy case, since those keep the whole row; a page of them is
# the reason `limit` is capped.
LIST_COLUMNS = (
    'id, batch_id, datasource_id, datasource_type, table_name, operation, '
    '"filter", filter_params, changes, meta, rows_affected, user_id, role_id, '
    'request_id, created_at'
)


def _build_where(filters: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Build the shared WHERE fragment and its bound parameters.

    One builder feeds both the page query and the COUNT, so the two can never
    disagree about what is being counted.
    """
    predicates = []
    params: Dict[str, Any] = {}

    for column in (
        'datasource_id',
        'batch_id',
        'table_name',
        'operation',
        'user_id',
        'request_id',
    ):
        value = filters.get(column)
        if value is not None:
            predicates.append(f'{column} = :{column}')
            params[column] = value

    if filters.get('filter') is not None:
        predicates.append('"filter" = :filter_exact')
        params['filter_exact'] = filters['filter']

    # Matched against the parsed predicate rather than the filter text, so it
    # does not care whether the caller wrote this column first or third, and
    # cannot false-positive on a value that happens to appear elsewhere in the
    # string. Several pairs AND together.
    for index, (column, value) in enumerate(
        sorted((filters.get('filter_params') or {}).items())
    ):
        # Both sides bound, never interpolated: the column name arrives from the
        # query string, and jsonb ->> takes it as a value rather than as SQL, so
        # there is nothing to escape.
        predicates.append(f'filter_params ->> :fp_key_{index} = :fp_val_{index}')
        params[f'fp_key_{index}'] = column
        params[f'fp_val_{index}'] = value

    if filters.get('from_date') is not None:
        predicates.append('created_at >= :from_date')
        params['from_date'] = filters['from_date']

    if filters.get('to_date') is not None:
        predicates.append('created_at <= :to_date')
        params['to_date'] = filters['to_date']

    where = ' AND '.join(predicates) if predicates else 'TRUE'
    return where, params


@datasource_audit_router.get('/v1/datasource-audit-logs')
@inject
async def list_datasource_audit_logs(
    request: Request,
    datasource_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    table_name: Optional[str] = None,
    operation: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    filter: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    audit_log_repository: SQLAlchemyRepository[DatasourceAuditLog] = Depends(
        Provide[PluginsContainer.datasource_audit_log_repository]
    ),
):
    """List audit records, newest first, each with its full `changes` document.

    Columns of the *mutated* row are addressed with a `param.` prefix and AND
    together: `?param.<column>=<value>`. Those match the parsed predicate, so a
    mutation is found only if the caller named that column in its filter — a row
    targeted by one of its columns is not findable by another, even though the
    row carries both.
    """
    if not await _can_read_audit_logs(request):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    # Checked before the query rather than after: these columns are uuid, so a
    # malformed value raises InvalidTextRepresentation and surfaces as a 500
    # with a SQL traceback instead of the 400 it should have been.
    for name, value in (('datasource_id', datasource_id), ('batch_id', batch_id)):
        if value is not None and not is_valid_uuid(value):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=response_formatter.buildErrorResponse(
                    f'Invalid {name}: {value}'
                ),
            )

    if operation is not None and operation not in VALID_OPERATIONS:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid operation: {operation}. '
                f'Expected one of: {", ".join(VALID_OPERATIONS)}'
            ),
        )

    where, params = _build_where(
        {
            'datasource_id': datasource_id,
            'batch_id': batch_id,
            'table_name': table_name,
            'operation': operation,
            # Never coerced to a UUID: service identities are literals like
            # 'hmac-service'.
            'user_id': user_id,
            'request_id': request_id,
            'filter': filter,
            'filter_params': _extract_filter_params(request),
            'from_date': from_date,
            'to_date': to_date,
        }
    )

    total_rows = await audit_log_repository.execute_query(
        f'SELECT COUNT(*) AS total FROM datasource_audit_logs WHERE {where}',
        params,
    )
    total = total_rows[0]['total'] if total_rows else 0

    logs = await audit_log_repository.execute_query(
        f'SELECT {LIST_COLUMNS} FROM datasource_audit_logs WHERE {where} '
        # id breaks ties: created_at is not unique under concurrent writes, and
        # an unstable sort makes offset pagination skip and repeat rows.
        'ORDER BY created_at DESC, id DESC LIMIT :limit OFFSET :offset',
        {**params, 'limit': limit, 'offset': offset},
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {
                # execute_query returns raw datetime/UUID objects.
                'logs': [serialize_values(log) for log in logs],
                'count': len(logs),
                'total': total,
                'offset': offset,
                'limit': limit,
            }
        ),
    )


@datasource_audit_router.get('/v1/datasource-audit-logs/{audit_log_id}')
@inject
async def get_datasource_audit_log(
    request: Request,
    audit_log_id: str,
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
    audit_log_repository: SQLAlchemyRepository[DatasourceAuditLog] = Depends(
        Provide[PluginsContainer.datasource_audit_log_repository]
    ),
):
    """One audit record by id.

    Returns the same fields the listing does; it exists for fetching a single
    record you already have the id of, typically from a `batch_id` or
    `request_id` you followed from somewhere else.
    """
    if not await _can_read_audit_logs(request):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=response_formatter.buildErrorResponse('Admin access required'),
        )

    if not is_valid_uuid(audit_log_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=response_formatter.buildErrorResponse(
                f'Invalid audit log id: {audit_log_id}'
            ),
        )

    audit_log = await audit_log_repository.find_one(id=audit_log_id)
    if not audit_log:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=response_formatter.buildErrorResponse(
                f'Audit log not found: {audit_log_id}'
            ),
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=response_formatter.buildSuccessResponse(
            {'log': audit_log.to_dict(include_changes=True)}
        ),
    )
