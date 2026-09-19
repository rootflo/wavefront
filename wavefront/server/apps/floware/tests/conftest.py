"""Test wiring specific to the floware app."""

from unittest.mock import Mock

import pytest
from db_repo_module.models.config import Config
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from flo_cloud.cloud_storage import CloudStorageManager
from flo_testing import make_test_client
from floware.controllers.config_controller import config_router
from floware.di.application_container import ApplicationContainer
from floware.services.config_service import ConfigService

CONFIG_CONTROLLER = 'floware.controllers.config_controller'


@pytest.fixture
def setup_containers(core_containers):
    core_containers.wire(
        core_containers.user,
        packages=[
            'user_management_module.authorization',
            'user_management_module.utils',
            'auth_module.controllers',
        ],
    )
    core_containers.wire(
        core_containers.common,
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
            'floware.controllers',
        ],
    )
    core_containers.wire(
        core_containers.auth,
        packages=['user_management_module.authorization'],
    )

    return core_containers.auth, core_containers.common


@pytest.fixture
def mock_cloud_storage_manager():
    mock_cloud = Mock(spec=CloudStorageManager)
    mock_cloud.save_small_file = Mock()
    mock_cloud.generate_presigned_url = Mock(
        return_value='https://mock-presigned-url.com/config.png'
    )
    return mock_cloud


@pytest.fixture
def mock_config_repository():
    mock_repo = Mock(spec=SQLAlchemyRepository[Config])
    mock_repo.upsert = Mock()
    mock_repo.find = Mock(return_value=[Mock(value={'app_icon': 'config.png'})])
    return mock_repo


@pytest.fixture
def mock_config():
    """App-level config for ApplicationContainer.

    Distinct from the harness's `user_config`, which configures UserContainer.
    """
    return {
        'floware': {
            'asset_storage_bucket': 'test-bucket',
            'config_file_name': 'config.png',
        }
    }


@pytest.fixture
def mock_config_service():
    mock_service = Mock(spec=ConfigService)

    async def mock_store_app_config(file, app_config_dict):
        return None

    async def mock_get_app_config():
        return 'https://test-bucket.com/config.png', {}

    async def mock_get_settings_config():
        return {
            'app_icon': 'https://test-bucket.com/config.png',
            'app_config': {},
            'datasources': [],
            'knowledge_bases': [],
        }

    mock_service.store_app_config = mock_store_app_config
    mock_service.get_app_config = mock_get_app_config
    mock_service.get_settings_config = mock_get_settings_config

    return mock_service


@pytest.fixture
def setup_application_container(
    core_containers,
    mock_cloud_storage_manager,
    mock_config_repository,
    mock_config,
    mock_config_service,
):
    app_container = ApplicationContainer()
    app_container.cloud_storage_manager.override(mock_cloud_storage_manager)
    app_container.config_repository.override(mock_config_repository)
    app_container.config.override(mock_config)
    app_container.config_service.override(mock_config_service)

    core_containers.wire(app_container, packages=['floware.controllers'])
    return app_container


@pytest.fixture
def test_client(setup_containers, setup_application_container):
    return make_test_client(config_router)


@pytest.fixture
def mock_auth_functions(patch_current_user):
    patch_current_user(
        'user_management_module.controllers.user_controller',
        role_id='test_user_id',
        user_id='test_role_id',
        session_id='test_session_id',
        include_user_utils=False,
    )


@pytest.fixture
def mock_admin_functions(patch_is_admin):
    patch_is_admin(CONFIG_CONTROLLER, include_user_utils=False)


@pytest.fixture
def mock_non_admin_functions(patch_is_admin):
    patch_is_admin(CONFIG_CONTROLLER, is_admin=False, include_user_utils=False)
