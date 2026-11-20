"""ServiceRegistry load ordering: one registry-wide counter, no per-id growth
for ids that don't exist, and a removal still beats an older in-flight load."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from api_services_module.config.registry import ServiceNotFoundError, ServiceRegistry


def registry_with(manager):
    registry = ServiceRegistry(api_service_manager=manager)
    registry.parser = MagicMock(
        parse_yaml_string=lambda _yaml: SimpleNamespace(id='acme')
    )
    registry.resolve_secrets = AsyncMock(side_effect=lambda definition: definition)
    registry.register_service = MagicMock()
    return registry


async def test_loading_missing_ids_leaves_no_state_behind():
    manager = MagicMock(get_api_service=AsyncMock(return_value=None))
    registry = registry_with(manager)

    for i in range(100):
        with pytest.raises(ServiceNotFoundError):
            await registry.load_service_from_db(f'missing-{i}')

    assert registry._removed_at == {}
    assert registry._registered_seq == {}


@pytest.mark.parametrize('remove', ['remove_service', 'deregister_service'])
async def test_a_removal_beats_an_older_in_flight_load(remove):
    gate = asyncio.Event()

    async def slow_fetch(_service):
        await gate.wait()
        return 'id: acme\n'

    manager = MagicMock(
        get_api_service=AsyncMock(return_value=SimpleNamespace(id='acme')),
        fetch_service_def=AsyncMock(side_effect=slow_fetch),
    )
    registry = registry_with(manager)

    load = asyncio.ensure_future(registry.load_service_from_db('acme'))
    await asyncio.sleep(0)
    getattr(registry, remove)('acme')  # removed while the load is in flight
    gate.set()
    assert await load is None  # the stale load returns without registering

    registry.register_service.assert_not_called()


async def test_a_load_registers_normally():
    manager = MagicMock(
        get_api_service=AsyncMock(return_value=SimpleNamespace(id='acme')),
        fetch_service_def=AsyncMock(return_value='id: acme\n'),
    )
    registry = registry_with(manager)

    await registry.load_service_from_db('acme')

    registry.register_service.assert_called_once()
