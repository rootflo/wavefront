import json
from urllib.parse import quote
import httpx

from common_module import runtime_settings


async def datasource_insert_rows(
    datasource_id: str, table_name: str, data, single_row: bool = False
) -> str:
    """Insert rows into a datasource table via wavefront's own REST API
    (POST /v1/datasources/{datasource_id}/resources/{resource_id}) — works
    against any configured datasource type (Postgres/BigQuery/Redshift/MSSQL),
    since that endpoint already dispatches generically via DatasourcePlugin.

    data: a single row dict if single_row=True, otherwise a list of row dicts.
    """
    rows = [data] if single_row else data

    url = (
        f'{runtime_settings.floware_base_url}/floware/v1/datasources/'
        f'{quote(datasource_id, safe="")}/resources/{quote(table_name, safe="")}'
    )
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json={'data': rows},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            return f"Failed to reach datasource API for '{datasource_id}': {e}"

    if response.status_code == 404:
        return f"Datasource '{datasource_id}' not found"
    if response.status_code != 200:
        return f'Insert failed ({response.status_code}): {response.text}'

    return f"Inserted {len(rows)} row(s) into '{table_name}' via datasource '{datasource_id}'"


async def datasource_insert_multi(datasource_id: str, inserts) -> str:
    """Insert rows into MULTIPLE tables of one datasource atomically (a single
    transaction — all-or-nothing) via wavefront's own REST API
    (POST /v1/datasources/{datasource_id}/resources/insert).

    inserts: a list of per-table specs, each
        {"table_name": str, "data": <single row dict or list of row dicts>,
         "single_row": bool (optional, default false)}.

    All tables are written in one DB transaction: any failure rolls back every
    table. Currently only Postgres datasources support this; others return 501.
    """
    url = (
        f'{runtime_settings.floware_base_url}/floware/v1/datasources/'
        f'{quote(datasource_id, safe="")}/resources/insert'
    )
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json={'inserts': inserts},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            return f"Failed to reach datasource API for '{datasource_id}': {e}"

    if response.status_code == 404:
        return f"Datasource '{datasource_id}' not found"
    if response.status_code != 200:
        return f'Multi-insert failed ({response.status_code}): {response.text}'

    table_count = len(inserts) if isinstance(inserts, list) else 0
    return (
        f"Inserted into {table_count} table(s) via datasource '{datasource_id}' "
        '(transactional)'
    )


def _error_message(response) -> str:
    """The API's own error text, or '' if the body is not the usual envelope.

    Failures come back as ``{"meta": {"status": "failure", "error": "..."}}``.
    That sentence names what was actually wrong; the raw body around it is noise
    to an agent, and on an unhandled error is a stack trace.
    """
    try:
        return response.json().get('meta', {}).get('error') or ''
    except (json.JSONDecodeError, AttributeError, TypeError):
        return ''


async def datasource_execute_query(
    datasource_id: str,
    query_id: str,
    params=None,
    filter: str = None,
    limit: int = 10,
    offset: int = 0,
    use_cache: bool = False,
) -> str:
    """Read data from a datasource by running a pre-registered dynamic query via
    wavefront's own REST API
    (POST /v1/{datasource_id}/dynamic-queries/{query_id}/execute).

    The SQL lives server-side in the query's YAML, so this reads joins and
    aggregates across several tables — unlike the table-at-a-time read route,
    which is restricted to a fixed whitelist.

    params: values for the named parameters the query declares, e.g.
        {"p_wavefront_run_id": "abc"}. Every value is sent as a string.
    filter: optional OData expression substituted for the query's {{filters}}
        placeholder (eq/gt/lt/lte/gte/contains/in, joined by $and / $or).
    use_cache: results are cached server-side for 2 minutes. Left false so a
        read that follows a write in the same workflow sees the write.

    Returns JSON mapping each query id in the YAML to its list of rows, e.g.
    {"quotes": [{...}, {...}]}. An empty list means nothing matched.
    """
    url = (
        f'{runtime_settings.floware_base_url}/floware/v1/'
        f'{quote(datasource_id, safe="")}/dynamic-queries/'
        f'{quote(query_id, safe="")}/execute'
    )

    # The OpenAI/Azure tool schema marks every parameter required regardless of
    # whether it has a default, so a model with nothing to say for these sends
    # them as null. Left as-is that reaches the endpoint as `?limit=`, which
    # fails to parse as an int — so fall back to the defaults here.
    limit = 10 if limit is None else limit
    offset = 0 if offset is None else offset

    # The endpoint types params as dict[str, str] and pydantic v2 does not coerce
    # numbers or booleans into strings — it 422s instead, so stringify here.
    query_params = {
        'offset': offset,
        'limit': limit,
        'force_fetch': 0 if use_cache else 1,
    }
    if filter:
        query_params['$filter'] = filter

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                params=query_params,
                json={'params': {k: str(v) for k, v in (params or {}).items()}},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            return f"Failed to reach datasource API for '{datasource_id}': {e}"

    if response.status_code == 404:
        # Two different things are missing under the same status — the datasource
        # or the query — and the agent can act on the difference: a bad query_id
        # is a misconfigured node, a bad datasource_id is a wiring error. The
        # server says which, so quote it rather than guessing.
        return (
            _error_message(response)
            or f"Datasource '{datasource_id}' or query '{query_id}' not found"
        )
    if response.status_code != 200:
        # A missing declared parameter still surfaces as a 500, so the body is
        # the only thing that says what went wrong.
        detail = _error_message(response) or response.text
        return f'Query execution failed ({response.status_code}): {detail}'

    try:
        results = response.json()['data']
    except (json.JSONDecodeError, KeyError, TypeError):
        return f'Unexpected response from datasource API: {response.text}'

    # Each query reports its own status: a failure comes back inside a 200, so
    # returning rows without checking would hand back an empty result set and no
    # indication that anything went wrong.
    rows_by_query = {}
    for sub_query_id, entry in results.items():
        if entry.get('status') == 'error':
            return f"Query '{sub_query_id}' failed: {entry.get('error')}"
        rows_by_query[sub_query_id] = entry.get('result', [])

    return json.dumps(rows_by_query)
