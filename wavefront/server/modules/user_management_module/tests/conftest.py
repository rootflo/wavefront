"""Test wiring specific to user_management_module.

The database, core containers, identity and seeding come from the flo-testing
plugin. The fixtures below are the per-controller auth setups: each controller
imports get_current_user/check_is_admin into its own namespace, so each needs
its own patch target.
"""

import pytest
from flo_testing import make_test_client
from user_management_module.router import user_management_router

ACCESS_CONTROLLER = 'user_management_module.controllers.access_controller'
GROUP_CONTROLLER = 'user_management_module.controllers.group_controller'
USER_CONTROLLER = 'user_management_module.controllers.user_controller'


@pytest.fixture
def setup_containers(core_containers):
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
            'user_management_module.controllers',
            'user_management_module.authorization',
        ],
    )
    core_containers.wire(
        core_containers.user,
        packages=[
            'user_management_module.authorization',
            'user_management_module.controllers',
            'user_management_module.utils',
            'auth_module.controllers',
        ],
    )
    # outlook_controller in auth_module.controllers resolves knowledge-base
    # providers, so that container has to be wired even though nothing here
    # exercises it.
    core_containers.wire(
        _knowledge_base_container(core_containers),
        packages=['auth_module.controllers'],
    )

    return core_containers.auth, core_containers.common, core_containers.user


def _knowledge_base_container(core_containers):
    from io import BytesIO
    from unittest.mock import Mock

    from knowledge_base_module.knowledge_base_container import (
        KnowledgeBaseContainer,
    )

    cloud_storage = Mock()
    cloud_storage.get_file = Mock(return_value=BytesIO(b'file content'))
    cloud_storage.read_file = Mock(return_value=b'file content')

    message_queue = Mock()
    message_queue.add_message = Mock(return_value='message_id_123')

    container = KnowledgeBaseContainer(
        db_client=core_containers.db_client,
        cache_manager=core_containers.cache_manager,
        cloud_storage_manager=cloud_storage,
        rag_queue=message_queue,
    )

    container.config.from_dict(
        {
            'cloud': {'provider': 'gcp'},
            'storage': {'application_bucket': 'test_bucket'},
        }
    )
    return container


@pytest.fixture
def mock_config(user_config):
    """The config the UserContainer was built with.

    The account-inactivity tests read `inactive_days_threshold` back out of it
    so their date arithmetic matches what the service is configured with.
    """
    return user_config


@pytest.fixture
def test_client(setup_containers):
    return make_test_client(user_management_router)


@pytest.fixture
def mock_auth_admin_functions(patch_auth):
    """Admin caller for the access (role/resource) endpoints."""
    patch_auth(
        ACCESS_CONTROLLER,
        role_id='test_user_id',
        user_id='test_role_id',
        session_id='test_session_id',
        include_user_utils=False,
    )


@pytest.fixture
def mock_group_admin_functions(patch_auth):
    patch_auth(
        GROUP_CONTROLLER,
        user_id='test_user_id',
        session_id='test_session_id',
        include_user_utils=False,
    )


@pytest.fixture
def mock_group_non_admin_functions(patch_auth):
    """Non-admin caller, for asserting the group endpoints reject them."""
    patch_auth(
        GROUP_CONTROLLER,
        is_admin=False,
        user_id='test_user_id',
        session_id='test_session_id',
        include_user_utils=False,
    )


@pytest.fixture
def mock_auth_admin_user_functions(patch_auth):
    """Admin caller for the user endpoints.

    Patches user_utils as well: the read endpoints go through can_read_users,
    which resolves both helpers from that namespace rather than the
    controller's.
    """
    patch_auth(USER_CONTROLLER, session_id='test_session_id')


@pytest.fixture
def mock_auth_non_admin_user_functions(patch_auth):
    patch_auth(USER_CONTROLLER, is_admin=False, session_id='test_session_id')


@pytest.fixture
def set_non_admin_data_access_flag(patch_feature_flag):
    """Toggle ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG for the user controller.

    Returns a setter rather than a value so one fixture serves both the flag-on
    and flag-off cases.
    """

    def _set(enabled: bool):
        patch_feature_flag(USER_CONTROLLER, enabled)

    return _set


@pytest.fixture
def mocking_user_controller_is_admin(patch_is_admin):
    patch_is_admin(USER_CONTROLLER)


@pytest.fixture
def mocking_user_controller_get_current_user(patch_current_user):
    patch_current_user(
        USER_CONTROLLER,
        role_id='wrong_role_id',
        session_id='test_session_id',
        include_user_utils=False,
    )
