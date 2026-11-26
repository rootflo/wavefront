"""Overload and outage errors answer 503 with Retry-After, not a 500."""

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from common_module.blocking_io import BlockingPoolBusyError
from common_module.security.public_key_cache import PublicKeyUnavailableError
from datasource.executor import DatasourceBusyError
from db_repo_module.cache.cache_manager import CacheUnavailableError

# Load the module from its file: importing the floware.app package builds the DI
# container, which needs the full deployment environment.
_spec = importlib.util.spec_from_file_location(
    'floware_exception_handlers_under_test',
    Path(__file__).resolve().parents[1] / 'floware' / 'app' / 'exception_handlers.py',
)
_handlers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_handlers)
register_exception_handlers = _handlers.register_exception_handlers


def client_raising(exc: Exception) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app, is_dev=False)

    @app.get('/boom')
    async def boom():
        raise exc

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    'exc',
    [
        BlockingPoolBusyError('storage', 10.0),
        CacheUnavailableError('Redis DEL failed: TimeoutError'),
        PublicKeyUnavailableError('Could not fetch the token public key'),
    ],
    ids=['pool-busy', 'cache-unavailable', 'kms-unavailable'],
)
def test_overload_is_a_503_with_retry_after(exc):
    response = client_raising(exc).get('/boom')

    assert response.status_code == 503
    assert int(response.headers['Retry-After']) >= 1
    assert 'Redis' not in response.text  # no internals in the body


def test_datasource_busy_is_a_503_with_retry_after():
    response = client_raising(DatasourceBusyError('all datasource threads busy')).get(
        '/boom'
    )

    assert response.status_code == 503
    assert int(response.headers['Retry-After']) >= 1


def test_other_errors_stay_500():
    response = client_raising(RuntimeError('bug')).get('/boom')

    assert response.status_code == 500
