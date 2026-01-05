from typing import Optional, Tuple
from fastapi import Request

from user_management_module.constants.auth import RootfloHeaders


def extract_auth_credentials(request: Request) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract access_token and app_key from request headers.

    Args:
        request: FastAPI Request object

    Returns:
        Tuple of (access_token, app_key), both can be None if not present
    """
    auth_header = request.headers.get('Authorization')
    access_token = None
    if auth_header:
        parts = auth_header.split(' ', 1)
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            access_token = parts[1]

    app_key = request.headers.get(RootfloHeaders.CLIENT_KEY)

    return access_token, app_key
