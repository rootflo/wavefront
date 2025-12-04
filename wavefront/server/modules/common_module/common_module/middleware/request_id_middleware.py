import re
import secrets
import string
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

# Context variable to store current request ID
request_id_context: ContextVar[str] = ContextVar('request_id', default='NO-REQUEST-ID')


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle X-Flo-Request-ID header for request tracing with prefix support.

    Features:
    - Checks for existing X-Flo-Request-ID header (case insensitive)
    - Validates that the ID format is: prefix-[8-12 alphanumeric characters]
    - Accepts prefixes: 'fe' (frontend) or 'be' (backend)
    - Generates new ID with 'be' prefix if missing or invalid
    - Stores ID in request.state and logging context
    - Adds X-Flo-Request-ID to response headers
    """

    # Regex pattern for prefix-[8-12 alphanumeric characters]
    REQUEST_ID_PATTERN = re.compile(r'^(fe|be)-[a-zA-Z0-9]{8,12}$')
    VALID_PREFIXES = {'fe', 'be'}

    @staticmethod
    def generate_request_id(prefix: str = 'be') -> str:
        if prefix not in RequestIdMiddleware.VALID_PREFIXES:
            prefix = 'be'  # Default to backend

        length = secrets.randbelow(5) + 8
        alphabet = string.ascii_letters + string.digits
        random_part = ''.join(secrets.choice(alphabet) for _ in range(length))
        return f'{prefix}-{random_part}'

    @staticmethod
    def validate_request_id(request_id: str) -> bool:
        return bool(RequestIdMiddleware.REQUEST_ID_PATTERN.match(request_id))

    @staticmethod
    def get_request_id_from_headers(request: Request) -> str | None:
        """Extract X-Flo-Request-ID from headers (case insensitive)."""
        for header_name, header_value in request.headers.items():
            if header_name.lower() == 'x-flo-request-id':
                return header_value
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        existing_request_id = self.get_request_id_from_headers(request)

        if existing_request_id and self.validate_request_id(existing_request_id):
            request_id = existing_request_id
        else:
            request_id = self.generate_request_id('be')

        request.state.request_id = request_id
        token = request_id_context.set(request_id)

        try:
            response = await call_next(request)
            response.headers['X-Flo-Request-ID'] = request_id
            return response
        finally:
            request_id_context.reset(token)


def get_current_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_context.get()
