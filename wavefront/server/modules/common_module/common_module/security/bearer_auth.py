"""Bearer token authentication scheme for FastAPI"""

from fastapi.security import HTTPBearer


class BearerAuth(HTTPBearer):
    """
    Custom HTTPBearer authentication scheme that maps to 'BearerAuth' in OpenAPI.

    This provides a centralized Bearer token authentication scheme that can be
    imported and used across all controllers to ensure consistent security
    configuration.

    Usage:
        from common_module.security.bearer_auth import bearer_auth
        from fastapi import Security

        @router.get('/endpoint', dependencies=[Security(bearer_auth)])
        async def my_endpoint():
            ...
    """

    def __init__(self):
        super().__init__(
            auto_error=False,  # Security validation handled by RequireAuthMiddleware
            scheme_name='BearerAuth',  # Must match OpenAPI components.securitySchemes name
            description='Enter your JWT Bearer token',
        )


# Singleton instance to be imported and used across the application
bearer_auth = BearerAuth()
