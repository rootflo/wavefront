import httpx
from common_module.common_container import CommonContainer
from common_module.log.logger import logger
from common_module.response_formatter import ResponseFormatter
from dependency_injector.wiring import inject
from dependency_injector.wiring import Provide
from deprecated_api_module.deprecated_api_container import DeprecatedApiContainer
from deprecated_api_module.services.audit_service_proxy import AuditServiceProxy
from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi import Response
from fastapi import status
from fastapi.responses import JSONResponse

image_controller = APIRouter()


@image_controller.post('/analyse', deprecated=True)
@inject
async def process_image(
    request: Request,
    audit_service_proxy: AuditServiceProxy = Depends(
        Provide[DeprecatedApiContainer.audit_service_proxy]
    ),
    response_formatter: ResponseFormatter = Depends(
        Provide[CommonContainer.response_formatter]
    ),
):
    """Deprecated: relays the request as-is to the audit API service."""
    body = await request.body()
    try:
        upstream = await audit_service_proxy.forward(
            body, request.headers, request.url.query
        )
    except httpx.RequestError as e:
        logger.error(f'Audit service unreachable at {audit_service_proxy.url}: {e}')
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=response_formatter.buildErrorResponse(
                'Audit service is unavailable'
            ),
        )

    unwrapped = _unwrap_api_service_envelope(upstream)
    if unwrapped is not None:
        return unwrapped

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get('content-type'),
    )


def _unwrap_api_service_envelope(upstream: httpx.Response) -> JSONResponse | None:
    """Return the audit service's own response from inside the API services
    envelope, so /analyse keeps its original ``{meta, data}`` shape.

    API services wraps the upstream reply as
    ``{meta, data: <upstream body>, http_status_code}``. Anything not in that
    shape (e.g. an auth failure raised by floware before the call is made) is
    left for the caller to pass through unchanged.
    """
    try:
        body = upstream.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    inner = body.get('data')
    if not isinstance(inner, dict) or 'meta' not in inner:
        return None

    status_code = body.get('http_status_code')
    if not isinstance(status_code, int):
        status_code = upstream.status_code
    return JSONResponse(status_code=status_code, content=inner)
