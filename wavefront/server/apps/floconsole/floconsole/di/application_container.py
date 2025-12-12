from dependency_injector import containers
from dependency_injector import providers

from flo_cloud.kms import FloKmsService
from floconsole.db import (
    DatabaseClient,
    DatabaseConfig,
    User,
    Session,
    App,
    SQLAlchemyRepository,
)
from floconsole.services.token_service import TokenService
from floconsole.services.floware_proxy_service import FlowareProxyService
from floconsole.services.app_service import AppService
from floconsole.services.user_service import UserService


class ApplicationContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['./config.ini'])

    # Common module container (external dependency)
    common_container = providers.Dependency()

    # Database configuration and client
    db_config = providers.Factory(
        DatabaseConfig,
        username=config.database.username,
        password=config.database.password,
        host=config.database.host,
        port=config.database.port,
        db_name=config.database.db_name,
    )

    db_client = providers.Singleton(DatabaseClient, db_config=db_config)

    # Repositories using generic SQLAlchemyRepository
    user_repository = providers.Singleton(
        SQLAlchemyRepository[User], model=User, db_client=db_client
    )

    session_repository = providers.Singleton(
        SQLAlchemyRepository[Session], model=Session, db_client=db_client
    )

    app_repository = providers.Singleton(
        SQLAlchemyRepository[App], model=App, db_client=db_client
    )

    # services
    app_service = providers.Singleton(AppService, app_repository=app_repository)

    user_service = providers.Factory(
        UserService,
        user_repository=user_repository,
    )

    kms_service = providers.Selector(
        config.jwt_token.enable_cloud_kms,
        true=providers.Singleton(
            FloKmsService, cloud_provider=config.cloud_config.cloud_provider
        ),
        false=providers.Object(None),  # No KMS service if cloud KMS is not enabled
    )

    token_service = providers.Singleton(
        TokenService,
        private_key=config.jwt_token.private_key,
        public_key=config.jwt_token.public_key,
        kms_service=kms_service,
        token_expiry=config.jwt_token.token_expiry,
        temporary_token_expiry=config.jwt_token.temporary_token_expiry,
        app_env=config.env_config.app_env,
        token_prefix=config.jwt_token.token_prefix,
        issuer=config.jwt_token.issuer,
        audience=config.jwt_token.audience,
    )

    # Floware proxy service
    floware_proxy_service = providers.Singleton(
        FlowareProxyService,
        token_service=token_service,
        app_service=app_service,
        service_issuer=config.jwt_token.issuer,
        app_env=config.env_config.app_env,
        token_prefix=config.jwt_token.token_prefix,
        temporary_token_expiry=config.jwt_token.temporary_token_expiry,
    )
