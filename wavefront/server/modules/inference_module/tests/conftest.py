"""Test wiring specific to inference_module."""

from unittest.mock import Mock

import pytest
from dependency_injector import providers
from flo_testing import make_test_client
from inference_module.controllers.inference_controller import inference_router
from inference_module.inference_container import InferenceContainer

INFERENCE_CONFIG = {
    'cloud_config': {'cloud_provider': 'gcp'},
    'gcp': {'model_storage_bucket': 'test_bucket'},
    'aws': {'model_storage_bucket': 'test_bucket'},
}


@pytest.fixture
def setup_containers(core_containers):
    inference_container = InferenceContainer(
        db_client=core_containers.db_client,
        cache_manager=core_containers.cache_manager,
    )

    cloud_storage_manager = Mock()
    cloud_storage_manager.save_large_file = Mock(return_value=None)
    inference_container.cloud_storage_manager.override(
        providers.Singleton(lambda: cloud_storage_manager)
    )
    inference_container.config.override(providers.Singleton(lambda: INFERENCE_CONFIG))

    core_containers.wire(inference_container, packages=['inference_module.controllers'])
    core_containers.wire(
        core_containers.common,
        packages=['auth_module.controllers', 'inference_module.controllers'],
    )
    core_containers.wire(
        core_containers.auth,
        packages=['user_management_module.authorization'],
    )
    core_containers.wire(
        core_containers.user,
        packages=['user_management_module.authorization'],
    )

    return core_containers.auth, core_containers.common, inference_container


@pytest.fixture
def test_client(setup_containers):
    return make_test_client(inference_router)
