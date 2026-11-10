"""Datasource read routes must not block the event loop while the DB is slow."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from datasource import PostgresConfig
from datasource.types import DataSourceType
from fastapi import FastAPI, Request

from common_module.common_container import CommonContainer
from dependency_injector import providers
from plugins_module.controllers import datasource_controller
from plugins_module.plugins_container import PluginsContainer

DATASOURCE_ID = '11111111-1111-1111-1111-111111111111'
RESOURCES_URL = f'/v1/datasources/{DATASOURCE_ID}/resources'
PG_CONFIG = PostgresConfig('h', 5432, 'db', 'u', 'p')
SLOW_DB_SECONDS = 0.5
MAX_LOOP_STALL = 0.2


@pytest.fixture(scope='module')
def app():
    container = CommonContainer()
    container.wire(modules=[datasource_controller])
    plugins = PluginsContainer()
    plugins.datasource_audit_service.override(
        providers.Object(MagicMock(capture_limit=100))
    )
    plugins.wire(modules=[datasource_controller])
    app = FastAPI()

    @app.middleware('http')
    async def session(request: Request, call_next):
        request.state.session = SimpleNamespace(role_id='role', user_id='user')
        return await call_next(request)

    app.include_router(datasource_controller.datasource_router)
    yield app
    plugins.unwire()
    container.unwire()


@pytest.fixture
def slow_plugin():
    def slow(result):
        def call(*args, **kwargs):
            time.sleep(SLOW_DB_SECONDS)  # a blocking driver call, like psycopg2
            return MagicMock(result=result)

        return call

    with (
        patch.object(
            datasource_controller, 'check_is_admin', AsyncMock(return_value=True)
        ),
        patch.object(
            datasource_controller,
            'get_datasource_config',
            AsyncMock(return_value=(DataSourceType.POSTGRES, PG_CONFIG)),
        ),
        patch.object(datasource_controller, 'DatasourcePlugin') as plugin_class,
    ):
        instance = plugin_class.return_value
        instance.get_table_names.side_effect = slow(['orders'])
        instance.fetch_data.side_effect = slow([{'id': 1}])
        yield instance


async def _max_loop_stall(app, url):
    """Return (response, longest gap between 10 ms heartbeat ticks)."""
    done = asyncio.Event()
    gaps = []

    async def heartbeat():
        last = time.perf_counter()
        while not done.is_set():
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            gaps.append(now - last)
            last = now

    ticker = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)  # let the heartbeat take its first timestamp
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        response = await client.get(url)
    done.set()
    await ticker
    return response, max(gaps)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'url',
    [RESOURCES_URL, f'{RESOURCES_URL}/orders'],
    ids=['get_tables', 'query_datasource'],
)
async def test_slow_datasource_does_not_block_event_loop(app, slow_plugin, url):
    response, stall = await _max_loop_stall(app, url)

    assert response.status_code == 200
    assert stall < MAX_LOOP_STALL, f'event loop was blocked for {stall:.2f}s'
