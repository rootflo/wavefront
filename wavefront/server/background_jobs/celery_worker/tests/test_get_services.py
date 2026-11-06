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
        'celery': {'broker_url': 'redis://localhost:6379/0'},
        'storage': {'application_bucket': '', 'account_url': ''},
        'cloud': {
            'platform': 'aws',
            'region': '',
            'project_id': '',
        },
        'hermes': {'url': ''},
    }

    with (
        patch.object(services, 'CONFIG', config),
        pytest.raises(ValueError, match='APPLICATION_BUCKET'),
    ):
        services.get_services()

    assert services._services is None


def test_worker_reads_llm_configs_from_floware_and_holds_no_cipher():
    from common_module.security.secret_cipher import UnavailableSecretCipher
    from llm_inference_config_module.clients.floware_llm_config_client import (
        FlowareLlmConfigClient,
    )

    container = services.ApplicationContainer()
    container.config.from_dict(
        {
            'env_config': {
                'base_url': 'http://floware:8001',
                'passthrough_secret': 'shh',
                'app_env': 'dev',
            }
        }
    )

    client = container.llm_config_client()
    assert isinstance(client, FlowareLlmConfigClient)
    assert client.base_url == 'http://floware:8001'
    assert client.passthrough_secret == 'shh'
    assert client.app_env == 'dev'
    assert isinstance(container.plugins.secret_cipher(), UnavailableSecretCipher)
    assert isinstance(container.api_services.secret_cipher(), UnavailableSecretCipher)
