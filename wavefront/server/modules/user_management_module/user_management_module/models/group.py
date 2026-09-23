from typing import List, Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import field_validator


def _reject_duplicates(values: Optional[List[str]], label: str) -> Optional[List[str]]:
    if values is not None and len(set(values)) != len(values):
        raise ValueError(f'{label} must be unique')
    return values


class CreateGroupPayload(BaseModel):
    """A group needs only a name. Roles and members can be filled in later, so
    both default to empty rather than being required."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    role_ids: List[str] = Field(default_factory=list, max_length=100)
    user_ids: List[str] = Field(default_factory=list, max_length=100)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError('Group name cannot be blank')
        return stripped

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v.strip() or None

    @field_validator('role_ids')
    @classmethod
    def validate_role_ids(cls, v):
        return _reject_duplicates(v, 'Role IDs')

    @field_validator('user_ids')
    @classmethod
    def validate_user_ids(cls, v):
        return _reject_duplicates(v, 'User IDs')


class UpdateGroupPayload(BaseModel):
    """Every field is optional and defaults to None.

    The None/empty-list distinction is load bearing for `role_ids`: None means
    "leave the group's roles alone", while [] means "remove every role from this
    group". Treating [] as a no-op would make it impossible to empty a group.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    role_ids: Optional[List[str]] = Field(None, max_length=100)

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError('Group name cannot be blank')
        return stripped

    @field_validator('description')
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return v.strip() or None

    @field_validator('role_ids')
    @classmethod
    def validate_role_ids(cls, v):
        return _reject_duplicates(v, 'Role IDs')


class GroupMembersPayload(BaseModel):
    user_ids: List[str] = Field(..., min_length=1, max_length=100)

    @field_validator('user_ids')
    @classmethod
    def validate_user_ids(cls, v):
        return _reject_duplicates(v, 'User IDs')
