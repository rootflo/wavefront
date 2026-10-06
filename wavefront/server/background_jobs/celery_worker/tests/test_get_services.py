"""get_services caching and required config guards."""

from unittest.mock import MagicMock, patch

import pytest

import celery_worker.services as services


@pytest.fixture(autouse=True)
def _clear_services_singleton():
    previous = services._services
    services._services = None
    yield
    services._services = previous


def test_get_services_returns_cached_singleton():
    sentinel = MagicMock(name='WorkerServices')
    services._services = sentinel
    assert services.get_services() is sentinel


def test_get_services_requires_application_bucket():
    config = {
        'database': {
            'username': 'u',
            'password': 'p',
            'host': 'localhost',
            'port': '5432',
            'db_name': 'floware',
            'pool_size': 1,
            'max_overflow': 0,
            'pool_timeout': 1,
            'pool_recycle': 1,
        },
        'env_config': {
            'base_url': 'http://localhost:8001',
            'passthrough_secret': '',
            'app_env': 'dev',
        },
        'storage': {'application_bucket': '', 'account_url': ''},
        'cloud': {
            'provider': 'aws',
            'region': '',
            'project_id': '',
            'location': '',
        },
        'hermes': {'url': ''},
    }

    db_repo = MagicMock()
    common = MagicMock()
    common.config.from_dict = MagicMock()

    with (
        patch.object(services, 'CONFIG', config),
        patch.object(services, '_build_db_client', return_value=MagicMock()),
        patch.object(services, 'DatabaseModuleContainer', return_value=db_repo),
        patch.object(services, 'CommonContainer', return_value=common),
        patch.object(services, 'configure_runtime_settings'),
        patch.object(services, 'create_api_services_container'),
        patch.object(services, 'PluginsContainer'),
        pytest.raises(ValueError, match='APPLICATION_BUCKET'),
    ):
        services.get_services()

    assert services._services is None
