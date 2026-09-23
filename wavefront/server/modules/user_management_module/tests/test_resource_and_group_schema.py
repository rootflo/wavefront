"""Unit tests for resource/role/group request schemas."""

import pytest
from pydantic import ValidationError

from user_management_module.models.group import CreateGroupPayload, GroupMembersPayload
from user_management_module.models.resource import (
    AddableResourceScope,
    CreateRolePayload,
    Resource,
    ResourcePayload,
)


def test_create_group_rejects_blank_name():
    with pytest.raises(ValidationError):
        CreateGroupPayload(name='   ')


def test_create_group_trims_name_and_bounds_description():
    group = CreateGroupPayload(name='  Eng  ', description='x' * 10)
    assert group.name == 'Eng'


def test_group_members_rejects_duplicates():
    with pytest.raises(ValidationError):
        GroupMembersPayload(user_ids=['a', 'a'])


def test_resource_dashboard_requires_meta():
    with pytest.raises(ValidationError):
        Resource(
            key='dash',
            value='Home',
            scope=AddableResourceScope.DASHBOARD,
            meta=None,
        )


def test_resource_dashboard_requires_meta_fields():
    with pytest.raises(ValidationError):
        Resource(
            key='dash',
            value='Home',
            scope=AddableResourceScope.DASHBOARD,
            meta='{"name":"Home"}',
        )


def test_resource_accepts_valid_dashboard_meta():
    resource = Resource(
        key='dash',
        value='Home',
        scope=AddableResourceScope.DASHBOARD,
        meta='{"name":"Home","key":"home","priority":1}',
    )
    assert resource.key == 'dash'


def test_resource_rejects_invalid_json_meta():
    with pytest.raises(ValidationError):
        Resource(
            key='data',
            value='v',
            scope=AddableResourceScope.DATA,
            meta='{not-json',
        )


def test_create_role_rejects_blank_name_and_duplicate_resources():
    with pytest.raises(ValidationError):
        CreateRolePayload(name='  ', resources=[])
    with pytest.raises(ValidationError):
        CreateRolePayload(name='Admin', resources=['r1', 'r1'])


def test_resource_payload_requires_at_least_one_resource():
    with pytest.raises(ValidationError):
        ResourcePayload(resources=[])
