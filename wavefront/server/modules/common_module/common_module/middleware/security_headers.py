"""
Security Headers Middleware for FastAPI

This middleware adds essential security headers to all HTTP responses to protect against
various web vulnerabilities and implement security best practices.

It lives in common_module so every app in the workspace (floware, floconsole,
call_processing, inference_app) serves one identical, reviewed set of headers.

Headers Implemented:
1. X-Content-Type-Options: nosniff
   - Prevents browsers from interpreting files as something other than their declared MIME type
   - Protects against MIME-type confusion attacks

2. X-XSS-Protection: 1; mode=block
   - Enables the built-in XSS filter in modern web browsers
   - Instructs browser to block rather than sanitize when XSS is detected

3. X-Frame-Options: SAMEORIGIN
   - Controls how your site can be embedded in iframes
   - Set to SAMEORIGIN to allow embedding only on the same origin
   - Prevents clickjacking attacks

4. Referrer-Policy: strict-origin-when-cross-origin
   - Controls how much information is included in the HTTP Referer header
   - Balances functionality with privacy by sending full URL for same-origin requests
   - Sends only origin for cross-origin requests

5. Content-Security-Policy: (path-dependent)
   - This app only ever serves JSON, so the default policy is a locked-down
     "default-src 'none'" API policy: no scripts, styles or frames of any kind
   - The interactive docs (/docs, /redoc) are the only HTML this app serves and
     they are dev-only, so they get their own relaxed policy scoped to those paths

6. Strict-Transport-Security: (production only)
   - Forces HTTPS connections when in production
   - Protects against protocol downgrade attacks

7. Cache-Control: no-store, no-cache, must-revalidate
   - Prevents caching of sensitive information
   - Ensures fresh content is always fetched from server
   - Protects against cache-based information leakage

8. Pragma: no-cache
   - Legacy cache control for HTTP/1.0 compatibility
   - Ensures older proxies and browsers don't cache responses

Usage:
    Add this middleware to your FastAPI app before CORS middleware:

    from common_module.middleware.security_headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)

Testing:
    Use the included test script to verify headers are properly set:

    python test_security_headers.py --url http://localhost:8001
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import os


# This app only ever serves JSON, so every fetch directive can be denied
# outright. 'unsafe-inline'/'unsafe-eval' are never granted here - they defeat
# the XSS protection CSP exists to provide, and nothing in the API needs them.
API_CSP = (
    "default-src 'none'; "
    "script-src 'none'; "
    "style-src 'none'; "
    "img-src 'none'; "
    "font-src 'none'; "
    "connect-src 'none'; "
    "object-src 'none'; "
    "media-src 'none'; "
    "frame-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

# Swagger UI / ReDoc are the only HTML this app serves, and they are dev-only
# (server.py leaves docs_url/redoc_url as None unless APP_ENV == 'dev'). They
# bootstrap from an inline <script> and pull their bundles from jsDelivr, so
# they need 'unsafe-inline' plus the CDN - scoped to the docs paths and to dev,
# so these tokens never reach a production response. ReDoc renders in a blob:
# worker.
_DOCS_CDN = 'https://cdn.jsdelivr.net'
DOCS_CSP = (
    "default-src 'self'; "
    f"script-src 'self' 'unsafe-inline' {_DOCS_CDN}; "
    f"style-src 'self' 'unsafe-inline' {_DOCS_CDN}; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    f"font-src 'self' data: {_DOCS_CDN}; "
    "connect-src 'self'; "
    'worker-src blob:; '
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Paths serving the interactive docs. FastAPI's swagger oauth2 redirect page
# lives under /docs, so a prefix match covers it.
DOCS_PATH_PREFIXES = ('/docs', '/redoc')


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-XSS-Protection: 1; mode=block - Enables XSS protection in browsers
    - X-Frame-Options: DENY - Controls iframe embedding
    - Referrer-Policy: strict-origin-when-cross-origin - Controls referrer information
    - Content-Security-Policy: locked-down API policy, relaxed only for dev docs
    - Cache-Control: no-store, no-cache, must-revalidate - Prevents caching
    - Pragma: no-cache - Legacy cache control for HTTP/1.0 compatibility
    - Expires: 0 - Prevents caching
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

        # Prefer process-wide settings from config.ini; fall back for apps that
        # have not called configure_runtime_settings yet.
        from common_module import runtime_settings

        self.environment = runtime_settings.app_env or os.getenv(
            'APP_ENV', 'production'
        )
        # The docs are only mounted in dev, so only there can a request reach
        # HTML that needs the relaxed policy.
        self.docs_enabled = self.environment == 'dev'

        # Configure static security headers based on environment
        self.static_security_headers = {
            # Prevent browsers from interpreting files as something other than declared MIME type
            'X-Content-Type-Options': 'nosniff',
            # Enable XSS filter in modern browsers
            'X-XSS-Protection': '1; mode=block',
            # No iframe embedding - matches frame-ancestors 'none' in API_CSP
            'X-Frame-Options': 'DENY',
            # Control referrer information
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            # Legacy cache control for HTTP/1.0 compatibility
            'Pragma': 'no-cache',
            # Prevent caching
            'Expires': '0',
            # Strict Transport Security (HTTPS only)
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains'
            if self.environment == 'production'
            else None,
        }

        # Remove None values
        self.static_security_headers = {
            k: v for k, v in self.static_security_headers.items() if v is not None
        }

    def _get_csp_header(self, request_path: str) -> str:
        """
        Select the Content Security Policy for a request path.

        Args:
            request_path: The path of the current request

        Returns:
            str: CSP header value
        """
        if self.docs_enabled and request_path.startswith(DOCS_PATH_PREFIXES):
            return DOCS_CSP
        return API_CSP

    def _get_cache_control_header(self, request_path: str) -> str:
        """
        Determine appropriate Cache-Control header based on the request path.

        Args:
            request_path: The path of the current request

        Returns:
            str: Cache-Control header value
        """
        return 'no-store, no-cache, must-revalidate, max-age=0'

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process the request and add security headers to the response.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or route handler

        Returns:
            Response: The HTTP response with security headers added
        """
        # Process the request
        response = await call_next(request)

        # Add static security headers to the response
        for header_name, header_value in self.static_security_headers.items():
            response.headers[header_name] = header_value

        # Add path-dependent headers
        response.headers['Content-Security-Policy'] = self._get_csp_header(
            request.url.path
        )
        cache_control = self._get_cache_control_header(request.url.path)
        response.headers['Cache-Control'] = cache_control

        return response
