"""Test wiring specific to auth_module (the superset controller)."""

from unittest.mock import Mock

import pytest
from auth_module.controllers.superset_controller import superset_controller
from flo_testing import make_test_client

SUPERSET_CONTROLLER = 'auth_module.controllers.superset_controller'


@pytest.fixture
def setup_containers(core_containers):
    # These tests exercise the real session lookup, so the user container's
    # cache has to miss rather than serve the canned session payload.
    cache_miss = Mock()
    cache_miss.get_str.return_value = None
    core_containers.user.cache_manager.override(cache_miss)

    core_containers.wire(
        core_containers.common,
        packages=[
            'user_management_module.controllers',
            'auth_module.controllers',
            'user_management_module.authorization',
        ],
    )
    core_containers.wire(
        core_containers.auth,
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
        ],
    )
    core_containers.wire(
        core_containers.user,
        packages=[
            'user_management_module.authorization',
            'auth_module.controllers',
        ],
    )

    return core_containers.auth, core_containers.common


@pytest.fixture
def test_client(setup_containers):
    # superset_controller carries its own full paths, so it mounts unprefixed.
    return make_test_client(superset_controller, prefix='')


@pytest.fixture
def mock_auth_functions(patch_is_admin):
    patch_is_admin(SUPERSET_CONTROLLER, include_user_utils=False)


@pytest.fixture
def mock_admin_false_functions(patch_is_admin):
    patch_is_admin(SUPERSET_CONTROLLER, is_admin=False, include_user_utils=False)
