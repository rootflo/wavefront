from db_repo_module.models.resource import Resource
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from user_management_module.services.user_service import UserService
from user_management_module.services.email_service import (
    OutlookEmailService,
    GmailEmailService,
)
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.services.account_inactivity_service import (
    AccountInactivityService,
)


class UserContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()
    user_repository = providers.Singleton(
        SQLAlchemyRepository[User], model=User, db_client=db_client
    )
    role_repository = providers.Singleton(
        SQLAlchemyRepository[Role], model=Role, db_client=db_client
    )
    resource_repository = providers.Singleton(
        SQLAlchemyRepository[Resource],
        model=Resource,
        db_client=db_client,
    )
    role_resource_repository = providers.Singleton(
        SQLAlchemyRepository[RoleResource],
        model=RoleResource,
        db_client=db_client,
    )
    user_role_repository = providers.Singleton(
        SQLAlchemyRepository[UserRole],
        model=UserRole,
        db_client=db_client,
    )
    session_repository = providers.Singleton(
        SQLAlchemyRepository[Session],
        model=Session,
        db_client=db_client,
    )

    auth_secrets_repository = providers.Singleton(
        SQLAlchemyRepository[AuthSecrets],
        model=AuthSecrets,
        db_client=db_client,
    )

    email_service = providers.Selector(
        selector=config.email.email_provider,
        outlook=providers.Singleton(
            OutlookEmailService,
            client_id=config.outlook.client_id,
            client_secret=config.outlook.client_secret,
            tenant_id=config.outlook.tenant_id,
            email_sender=config.outlook.email_id,
        ),
        gmail=providers.Singleton(
            GmailEmailService,
            service_account_b64=config.gmail.service_account_file,
            email_sender=config.gmail.email_sender,
            delegate_user=config.gmail.delegate_user,
        ),
    )

    user_service = providers.Singleton(
        UserService,
        user_repository=user_repository,
        user_role_repository=user_role_repository,
        session_repository=session_repository,
        resource_repository=resource_repository,
        cache_manager=cache_manager,
    )

    account_lockout_service = providers.Singleton(
        AccountLockoutService,
        user_repository=user_repository,
        cache_manager=cache_manager,
        max_failed_attempts=config.auth.max_failed_attempts,
        lockout_duration_hours=config.auth.lockout_duration_hours,
    )

    account_inactivity_service = providers.Singleton(
        AccountInactivityService,
        user_repository=user_repository,
        inactive_days_threshold=config.auth.inactive_days_threshold,
    )
