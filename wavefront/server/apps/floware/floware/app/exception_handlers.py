"""HTTP exception handlers for the floware FastAPI app."""

from common_module.log.logger import logger
from common_module.middleware.request_id_middleware import get_current_request_id
from common_module.response_formatter import ResponseFormatter
from common_module.telemetry import record_exception_on_span
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from flo_ai.llm.guarded_llm import GuardrailBlocked


def register_exception_handlers(app: FastAPI, *, is_dev: bool) -> None:
    @app.exception_handler(GuardrailBlocked)
    async def guardrail_blocked_handler(request: Request, exc: GuardrailBlocked):
        """Turn a policy block into a plain error response.

        A block is the guardrail working, not the server failing. Left to the
        catch-all below, it arrives as an unhandled exception: a ~100-frame
        traceback logged twice — once by that handler's ``exc_info``, then again
        by uvicorn, because Starlette re-raises whatever reaches its 500 handler
        — for an outcome whose whole explanation fits on one line.

        Which adapter fired, on which finding, under which policy version goes to
        the log only. The response carries the decision's own caller message,
        which deliberately names none of that: telling whoever tripped a check
        exactly which check they tripped is a map of how to phrase the next
        attempt.
        """
        request_id = getattr(request.state, 'request_id', get_current_request_id())
        detail = exc.decision.operator_summary() if exc.decision else str(exc)

        # A content block is the control doing its job. A block because a check
        # could not run - provider down with FAIL_CLOSED, or a policy naming an
        # adapter that is not registered - is rejecting legitimate traffic until
        # someone intervenes, and stays at error level so alerting still sees it.
        emit = (
            logger.error
            if exc.decision is not None and exc.decision.blocked_by_failure
            else logger.warning
        )
        emit(
            f'Guardrail blocked {request.method} {request.url.path} '
            f'[Request ID: {request_id}]: {detail}'
        )

        return JSONResponse(
            status_code=500,
            content=ResponseFormatter().buildErrorResponse(error=str(exc)),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # Skip HTTPExceptions (they're handled by FastAPI)
        if isinstance(exc, HTTPException):
            raise exc

        # This handler swallows the exception and returns a 500 without re-raising,
        # so it never reaches the OTel ASGI middleware's own exception recording -
        # the SERVER span would otherwise be marked as a success. Record it here.
        record_exception_on_span(exc)

        error_message = (
            'An unexpected error has occurred while performing this action, '
            'please try again'
        )
        if is_dev:
            error_message += f' - {str(exc)}'

        request_id = getattr(request.state, 'request_id', get_current_request_id())
        logger.error(
            f'Error in API call [Request ID: {request_id}]: {exc}', exc_info=True
        )

        exception_response_formatter = ResponseFormatter()
        return JSONResponse(
            status_code=500,
            content=exception_response_formatter.buildErrorResponse(
                error=error_message
            ),
        )
