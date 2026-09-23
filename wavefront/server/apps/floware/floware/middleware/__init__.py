"""
Middleware package for Floware application.
"""

from common_module.middleware.security_headers import SecurityHeadersMiddleware

from .setup import add_middlewares

__all__ = ['SecurityHeadersMiddleware', 'add_middlewares']
