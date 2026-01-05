from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel


class Meta(BaseModel):
    status: str
    code: int
    error: Optional[str] = None


class ResponseModel(BaseModel):
    meta: Meta
    data: Optional[Dict[str, Any]] = None


# Generic type variable
T = TypeVar('T')


class GenericResponseModel(BaseModel, Generic[T]):
    """Generic response model that can accept any type for data field"""

    meta: Meta
    data: Optional[T] = None


class DataWrapper(BaseModel, Generic[T]):
    """
    Generic wrapper for response data with message.
    """

    message: str
    data: T
