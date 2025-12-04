from auth_module.services.client_token_service import ClientTokenService
from auth_module.services.outlook_service import OutlookService
from auth_module.services.superset_service import SupersetService
from auth_module.services.token_service import TokenService
from common_module.feature.feature_flag import is_feature_enabled
from common_module.feature.feature_flag import SUPERSET_FLAG
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.models.resource import Resource
from db_repo_module.models.role import Role
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from flo_cloud.kms import FloKmsService


class AuthContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])

    db_client = providers.Dependency()
    cache_manager = providers.Dependency()

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
        issuer=config.jwt_token.issuer,
        audience=config.jwt_token.audience,
    )

    client_token_service = providers.Singleton(
        ClientTokenService,
        private_key_pem=config.app_config.client_secret,
        client_id=config.app_config.client_id,
        product_id=config.app_config.product_id,
    )

    if is_feature_enabled(SUPERSET_FLAG):
        superset_service = providers.Singleton(
            SupersetService,
            url=config.superset.url,
            username=config.superset.username,
            password=config.superset.password,
            cache_manager=cache_manager,
        )

    active_subscriptions = providers.Singleton(dict)

    outlook_service = providers.Singleton(
        OutlookService,
        client_id=config.outlook.client_id,
        client_secret=config.outlook.client_secret,
        tenant_id=config.outlook.tenant_id,
        email_id=config.outlook.email_id,
        authority=config.outlook.authority,
        webhook_url=config.outlook.webhook_url,
        active_subscriptions=active_subscriptions,
        cache_manager=cache_manager,
    )
