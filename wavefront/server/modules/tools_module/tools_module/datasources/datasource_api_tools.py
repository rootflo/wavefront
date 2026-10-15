import base64
import json
import posixpath
from urllib.parse import quote
import flo_lib.http as httpx
from flo_ai import ImageMessageContent, VideoMessageContent

from tools_module.floware_api import FlowareApiClient


async def datasource_insert_rows(
    api: FlowareApiClient,
    /,
    datasource_id: str,
    table_name: str,
    data,
    single_row: bool = False,
) -> str:
    """Insert rows into a datasource table via wavefront's own REST API
    (POST /v1/datasources/{datasource_id}/resources/{resource_id}) — works
    against any configured datasource type (Postgres/BigQuery/Redshift/MSSQL),
    since that endpoint already dispatches generically via DatasourcePlugin.

    data: a single row dict if single_row=True, otherwise a list of row dicts.
    """
    rows = [data] if single_row else data

    url = (
        f'{api.base_url}/floware/v1/datasources/'
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


async def datasource_insert_multi(
    api: FlowareApiClient, /, datasource_id: str, inserts
) -> str:
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
        f'{api.base_url}/floware/v1/datasources/'
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
    api: FlowareApiClient,
    /,
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
        f'{api.base_url}/floware/v1/'
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


# Whatever the tool returns lands in the model's context, so a large object is
# refused rather than inlined (base64 also grows binary content by a third).
MAX_DOWNLOAD_BYTES = 5 * 1024 * 1024
# Images and videos go to the model as media, not text; 20 MB is Gemini's
# inline request limit, the tightest of the providers that take video.
MAX_MEDIA_DOWNLOAD_BYTES = 20 * 1024 * 1024
# Image formats every vision provider accepts; others (SVG, TIFF, BMP) fall
# back to text/base64.
MODEL_IMAGE_TYPES = frozenset({'image/png', 'image/jpeg', 'image/gif', 'image/webp'})


async def datasource_download_file(
    api: FlowareApiClient,
    /,
    datasource_id: str,
    path: str,
) -> str | ImageMessageContent | VideoMessageContent:
    """Download one file from a file storage datasource (S3, GCS or Azure Blob)
    via wavefront's own REST API (GET /v1/datasources/{datasource_id}/files).

    path: the path an upload returned, "datasource://<datasource_id>/<key>"
        (it must name this datasource), or a key relative to the datasource's
        base path ("reports/q1.csv").

    Images (PNG, JPEG, GIF, WebP) and videos come back as ImageMessageContent
    / VideoMessageContent, which the agent adds to the conversation as media
    the model can see. Anything else returns JSON {"path", "content_type",
    "size_bytes", "encoding", "content"}: "content" is the text itself when
    the bytes are UTF-8, otherwise base64 with "encoding": "base64".
    """
    url = f'{api.base_url}/floware/v1/datasources/{quote(datasource_id, safe="")}/files'
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                url,
                params={'path': path},
                headers=api.headers(),
                timeout=60.0,
            )
        except httpx.RequestError as e:
            return f"Failed to reach datasource API for '{datasource_id}': {e}"

    if response.status_code == 404:
        # Either the datasource or the file is missing; the server says which.
        return (
            _error_message(response)
            or f"File '{path}' not found in datasource '{datasource_id}'"
        )
    if response.status_code != 200:
        detail = _error_message(response) or response.text
        return f'File download failed ({response.status_code}): {detail}'

    content = response.content
    content_type = response.headers.get('content-type', '')
    mime_type = content_type.split(';')[0].strip().lower()
    if mime_type in MODEL_IMAGE_TYPES:
        media_class = ImageMessageContent
    elif mime_type.startswith('video/'):
        media_class = VideoMessageContent
    else:
        media_class = None

    limit = MAX_MEDIA_DOWNLOAD_BYTES if media_class else MAX_DOWNLOAD_BYTES
    if len(content) > limit:
        return (
            f"File '{path}' is {len(content)} bytes, over the "
            f'{limit}-byte limit for this tool'
        )

    if media_class is not None:
        return media_class(
            base64=base64.b64encode(content).decode('ascii'),
            mime_type=mime_type,
            file_name=posixpath.basename(path.rstrip('/')) or None,
        )

    try:
        encoding, body = 'utf-8', content.decode('utf-8')
    except UnicodeDecodeError:
        encoding, body = 'base64', base64.b64encode(content).decode('ascii')

    return json.dumps(
        {
            'path': path,
            'content_type': content_type,
            'size_bytes': len(content),
            'encoding': encoding,
            'content': body,
        }
    )
