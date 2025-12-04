"""
Security Headers Middleware for FastAPI

This middleware adds essential security headers to all HTTP responses to protect against
various web vulnerabilities and implement security best practices.

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

5. Content-Security-Policy: (environment-dependent)
   - Defines trusted sources for various content types
   - Helps prevent XSS attacks by restricting resource loading
   - Different policies for development vs production environments

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

    app.add_middleware(SecurityHeadersMiddleware)

Testing:
    Use the included test script to verify headers are properly set:

    python test_security_headers.py --url http://localhost:8001
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import os


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - X-XSS-Protection: 1; mode=block - Enables XSS protection in browsers
    - X-Frame-Options: SAMEORIGIN - Controls iframe embedding
    - Referrer-Policy: strict-origin-when-cross-origin - Controls referrer information
    - Content-Security-Policy: Basic CSP for additional protection
    - Cache-Control: no-store, no-cache, must-revalidate - Prevents caching
    - Pragma: no-cache - Legacy cache control for HTTP/1.0 compatibility
    - Expires: 0 - Prevents caching
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

        # Get environment-specific configuration
        self.environment = os.getenv('APP_ENV', 'dev')

        # Configure static security headers based on environment
        self.static_security_headers = {
            # Prevent browsers from interpreting files as something other than declared MIME type
            'X-Content-Type-Options': 'nosniff',
            # Enable XSS filter in modern browsers
            'X-XSS-Protection': '1; mode=block',
            # Control iframe embedding - allow same origin
            'X-Frame-Options': 'SAMEORIGIN',
            # Control referrer information
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            # Basic Content Security Policy
            'Content-Security-Policy': self._get_csp_header(),
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

    def _get_csp_header(self) -> str:
        """
        Generate Content Security Policy header based on environment.

        Returns:
            str: CSP header value
        """
        if self.environment == 'production':
            # Stricter CSP for production
            return (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'self'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            # More permissive CSP for development
            return (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' http://localhost:* ws://localhost:*; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https: http:; "
                "font-src 'self' data:; "
                "connect-src 'self' http://localhost:* ws://localhost:*; "
                "frame-ancestors 'self'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

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

        # Add dynamic cache control header based on request path
        cache_control = self._get_cache_control_header(request.url.path)
        response.headers['Cache-Control'] = cache_control

        return response
