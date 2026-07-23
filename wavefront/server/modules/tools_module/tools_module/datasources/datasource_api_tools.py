import os
from urllib.parse import quote
import httpx

FLOWARE_BASE_URL = os.getenv('FLOWARE_BASE_URL', 'http://localhost:8001').rstrip('/')


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
        f'{FLOWARE_BASE_URL}/floware/v1/datasources/'
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
    (POST /v1/datasources/{datasource_id}/resources).

    inserts: a list of per-table specs, each
        {"table_name": str, "data": <single row dict or list of row dicts>,
         "single_row": bool (optional, default false)}.

    All tables are written in one DB transaction: any failure rolls back every
    table. Currently only Postgres datasources support this; others return 501.
    """
    url = (
        f'{FLOWARE_BASE_URL}/floware/v1/datasources/'
        f'{quote(datasource_id, safe="")}/resources'
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
