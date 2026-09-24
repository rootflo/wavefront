from dependency_injector import containers
from dependency_injector import providers

from flo_cloud.kms import FloKmsSigner
from flo_cloud._types import KmsKeySettings
from floconsole.db import (
    DatabaseClient,
    DatabaseConfig,
    User,
    Session,
    App,
    SQLAlchemyRepository,
)
from floconsole.db.models.app_user import AppUser
from floconsole.services.token_service import TokenService
from floconsole.services.floware_proxy_service import FlowareProxyService
from floconsole.services.app_service import AppService
from floconsole.services.user_service import UserService
from floconsole.services.app_user_service import AppUserService


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

    app_user_repository = providers.Singleton(
        SQLAlchemyRepository[AppUser], model=AppUser, db_client=db_client
    )

    # services
    app_service = providers.Singleton(AppService, app_repository=app_repository)

    user_service = providers.Factory(
        UserService,
        user_repository=user_repository,
    )

    app_user_service = providers.Singleton(
        AppUserService,
        app_user_repository=app_user_repository,
    )

    kms_signing_settings = providers.Factory(
        KmsKeySettings,
        provider=config.cloud.provider,
        key=config.kms_signing.key,
        key_version=config.kms_signing.key_version,
        key_ring=config.kms_signing.key_ring,
        project_id=config.cloud.project_id,
        location=config.cloud.location,
        region=config.cloud.region,
        vault_url=config.azure.key_vault_url,
        client_id=config.azure.client_id,
        client_secret=config.azure.client_secret,
        tenant_id=config.azure.tenant_id,
    )

    kms_signer = providers.Selector(
        config.jwt_token.enable_cloud_kms,
        true=providers.Singleton(FloKmsSigner, settings=kms_signing_settings),
        false=providers.Object(None),
    )

    token_service = providers.Singleton(
        TokenService,
        private_key=config.jwt_token.private_key,
        public_key=config.jwt_token.public_key,
        kms_signer=kms_signer,
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
        user_service=user_service,
        service_issuer=config.jwt_token.issuer,
        app_env=config.env_config.app_env,
        token_prefix=config.jwt_token.token_prefix,
        temporary_token_expiry=config.jwt_token.temporary_token_expiry,
        passthrough_secret=config.env_config.passthrough_secret,
    )
