from enum import Enum
import json
from typing import List, Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


class AddableResourceScope(str, Enum):
    DASHBOARD = 'dashboard'
    DATA = 'data'
    ROUTE = 'route'


class Resource(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=500)
    scope: AddableResourceScope
    meta: Optional[str] = Field(None, max_length=4000)

    @field_validator('meta')
    @classmethod
    def validate_meta_for_scope(
        cls, meta: Optional[str], values: dict
    ) -> Optional[str]:
        if not meta:
            if values.data.get('scope') == AddableResourceScope.DASHBOARD:
                raise ValueError('meta is required for dashboard resources')
            return meta

        try:
            meta_dict = json.loads(meta)
        except json.JSONDecodeError:
            raise ValueError('meta must be a valid JSON string')

        scope = values.data.get('scope')
        if scope == AddableResourceScope.DASHBOARD:
            required_fields = ['name', 'key', 'priority']
            if not all(field in meta_dict for field in required_fields):
                raise ValueError(
                    f"Dashboard resources must include {', '.join(required_fields)} in meta"
                )

        return meta


class ResourcePayload(BaseModel):
    resources: List[Resource] = Field(..., min_length=1, max_length=100)


class Role(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., max_length=500)


class CreateRolePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    resources: List[str] = Field(..., max_length=100)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError('Role name cannot be blank')
        return stripped

    @field_validator('resources')
    @classmethod
    def validate_resources(cls, v: List[str]) -> List[str]:
        if len(set(v)) != len(v):
            raise ValueError('Resource IDs must be unique')
        for item in v:
            if not item or not str(item).strip():
                raise ValueError('Resource IDs must be non-empty')
            if len(str(item)) > 100:
                raise ValueError('Resource IDs must be at most 100 characters')
        return v


class UpdateRolePayload(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    resources: Optional[List[str]] = Field(None, max_length=100)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError('Role name cannot be blank')
        return stripped

    @field_validator('resources')
    @classmethod
    def validate_resources(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        if len(set(v)) != len(v):
            raise ValueError('Resource IDs must be unique')
        for item in v:
            if not item or not str(item).strip():
                raise ValueError('Resource IDs must be non-empty')
            if len(str(item)) > 100:
                raise ValueError('Resource IDs must be at most 100 characters')
        return v


class UpdateResourcePayload(BaseModel):
    key: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=500)
    scope: Optional[AddableResourceScope] = None
    meta: Optional[str] = Field(None, max_length=4000)
