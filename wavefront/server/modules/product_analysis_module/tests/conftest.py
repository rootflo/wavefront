"""Test wiring specific to product_analysis_module.

The database, the core containers, identity and seeding all come from the
flo-testing plugin; what is left here is this module's own container and router.
"""

import pytest
from flo_testing import make_test_client
from product_analysis_module.controllers.product_anaysis_controllers import (
    product_analysis_router,
)
from product_analysis_module.product_analysis_container import (
    ProductAnalysisContainer,
)

CONTROLLERS = 'product_analysis_module.controllers.product_anaysis_controllers'


@pytest.fixture
def setup_containers(core_containers):
    product_analysis_container = ProductAnalysisContainer()

    core_containers.wire(
        product_analysis_container,
        packages=['product_analysis_module.controllers'],
    )
    core_containers.wire(
        core_containers.db_repo,
        packages=['product_analysis_module.product_analysis_service'],
    )
    core_containers.wire(
        core_containers.common,
        packages=[
            'auth_module.controllers',
            'user_management_module.authorization',
            'product_analysis_module.controllers',
        ],
    )
    core_containers.wire(
        core_containers.auth,
        packages=['user_management_module.authorization'],
    )
    core_containers.wire(
        core_containers.user,
        packages=[
            'user_management_module.authorization',
            'user_management_module.utils',
            'auth_module.controllers',
        ],
    )

    return core_containers.auth, core_containers.common, product_analysis_container


@pytest.fixture
def test_client(setup_containers):
    return make_test_client(product_analysis_router)


@pytest.fixture
def mock_auth_functions(patch_auth):
    patch_auth('user_management_module.controllers.user_controller')


@pytest.fixture
def mock_admin_functions(patch_auth):
    patch_auth(CONTROLLERS, is_admin=True)


@pytest.fixture
def mock_non_admin_functions(patch_auth):
    patch_auth(is_admin=False)
