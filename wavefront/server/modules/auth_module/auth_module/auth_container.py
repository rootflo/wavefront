from auth_module.services.superset_service import SupersetService
from auth_module.services.token_service import TokenService
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.models.resource import Resource
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers


def _validation_issuers(raw: str | None) -> list[str]:
    return [issuer.strip() for issuer in (raw or '').split(',') if issuer.strip()]


class AuthContainer(containers.DeclarativeContainer):
    config = providers.Configuration()

    db_client = providers.Dependency()
    cache_manager = providers.Dependency()
    kms_signer = providers.Dependency()

    resource_repository = providers.Singleton(
        SQLAlchemyRepository[Resource],
        model=Resource,
        db_client=db_client,
    )

    role_repository = providers.Singleton(
        SQLAlchemyRepository[Role],
        model=Role,
        db_client=db_client,
    )

    auth_secrets_repository = providers.Singleton(
        SQLAlchemyRepository[AuthSecrets],
        model=AuthSecrets,
        db_client=db_client,
    )

    token_service = providers.Singleton(
        TokenService,
        kms_signer=kms_signer,
        token_expiry=config.jwt_token.token_expiry.as_int(),
        temporary_token_expiry=config.jwt_token.temporary_token_expiry.as_int(),
        app_env=config.env_config.app_env,
        issuer=config.jwt_token.issuer,
        audience=config.jwt_token.audience,
        validation_issuers=providers.Callable(
            _validation_issuers, config.jwt_token.validation_issuer
        ),
        token_prefix=config.jwt_token.console_token_prefix,
    )

    # Always registered. Singleton is lazy, so an empty Superset URL costs
    # nothing until a request builds it. The route returns 404 when the flag
    # is off.
    superset_service = providers.Singleton(
        SupersetService,
        url=config.superset.url,
        username=config.superset.username,
        password=config.superset.password,
        cache_manager=cache_manager,
        cloud_provider=config.cloud.platform,
    )

    active_subscriptions = providers.Singleton(dict)
