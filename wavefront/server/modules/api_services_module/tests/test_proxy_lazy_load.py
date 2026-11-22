"""A proxy whose registry does not have a service yet (a replica that missed the create) finds it on first use."""

import pytest

from api_services_module.config.registry import ServiceRegistry
from api_services_module.core.proxy import ApiProxy


async def test_unloaded_registry_loads_the_service_on_first_use(
    mock_api_services_manager,
):
    registry = ServiceRegistry(mock_api_services_manager)  # load_from_db never ran
    proxy = ApiProxy(
        service_registry=registry, api_services_manager=mock_api_services_manager
    )
    assert registry.get_service('another-service') is None

    service = await proxy._load_missing_service('another-service')

    assert service is not None and service.id == 'another-service'
    assert registry.get_service('another-service') is service
    assert proxy.auth_manager.get_auth_handler('another-service') is not None


async def test_unknown_service_is_still_not_found(mock_api_services_manager):
    registry = ServiceRegistry(mock_api_services_manager)
    proxy = ApiProxy(
        service_registry=registry, api_services_manager=mock_api_services_manager
    )

    assert await proxy._load_missing_service('no-such-service') is None


async def test_invalid_stored_definition_is_not_reported_as_not_found(
    mock_api_services_manager,
):
    await mock_api_services_manager.create_api_service(
        id='broken-service', service_def_yaml='service:\n  id: broken-service\n'
    )
    registry = ServiceRegistry(mock_api_services_manager)
    proxy = ApiProxy(
        service_registry=registry, api_services_manager=mock_api_services_manager
    )

    with pytest.raises(ValueError, match='base_url'):
        await proxy._load_missing_service('broken-service')
