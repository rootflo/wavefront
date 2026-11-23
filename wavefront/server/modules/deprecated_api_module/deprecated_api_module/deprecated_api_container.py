from dependency_injector import containers
from dependency_injector import providers
from deprecated_api_module.services.audit_service_proxy import AuditServiceProxy


class DeprecatedApiContainer(containers.DeclarativeContainer):
    floware_base_url = providers.Dependency()

    audit_service_proxy = providers.Singleton(
        AuditServiceProxy,
        floware_base_url=floware_base_url,
    )
