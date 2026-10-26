"""A proxy whose registry was never loaded (the Celery worker) finds services on first use."""

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
