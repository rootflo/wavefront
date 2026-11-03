from typing import Annotated

from authz_module import Principal, principal_of
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status


async def get_current_session(request: Request) -> Principal:
    """The authenticated caller."""
    principal = principal_of(request)
    if principal.is_anonymous:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated'
        )
    return principal


CurrentSession = Annotated[Principal, Depends(get_current_session)]
