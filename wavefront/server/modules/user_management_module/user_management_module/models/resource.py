from enum import Enum
import json
from typing import List, Optional

from pydantic import BaseModel
from pydantic import field_validator


class AddableResourceScope(str, Enum):
    DASHBOARD = 'dashboard'
    DATA = 'data'


class Resource(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    scope: AddableResourceScope
    meta: Optional[str] = None

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
    resources: List[Resource]


class Role(BaseModel):
    id: str
    name: str
    description: str


class CreateRolePayload(BaseModel):
    name: str
    description: Optional[str]
    resources: List[str]


class UpdateResourcePayload(BaseModel):
    key: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[AddableResourceScope] = None
    meta: Optional[str] = None
