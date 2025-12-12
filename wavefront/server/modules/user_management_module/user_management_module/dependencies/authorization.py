from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import status


@dataclass
class UserSession:
    role: str
    user_id: str


async def get_current_session(request: Request) -> UserSession:
    """Get the current user session from request state"""
    session = getattr(request.state, 'session', None)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Not authenticated'
        )
    return session


async def check_admin_role(
    session: Annotated[UserSession, Depends(get_current_session)],
) -> UserSession:
    """Check if the current user has admin role"""
    if session.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='Admin privileges required'
        )
    return session


CurrentSession = Annotated[UserSession, Depends(get_current_session)]
AdminSession = Annotated[UserSession, Depends(check_admin_role)]
