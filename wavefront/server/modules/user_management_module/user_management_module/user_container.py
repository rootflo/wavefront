from db_repo_module.models.resource import Resource
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.session import Session
from db_repo_module.models.user import User
from db_repo_module.models.user_group import UserGroup
from db_repo_module.models.user_group_member import UserGroupMember
from db_repo_module.models.user_group_role import UserGroupRole
from db_repo_module.models.user_role import UserRole
from db_repo_module.models.auth_secrets import AuthSecrets
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector import containers
from dependency_injector import providers
from user_management_module.services.user_service import UserService
from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.services.account_inactivity_service import (
    AccountInactivityService,
)
from user_management_module.services.recaptcha_service import RecaptchaService


class UserContainer(containers.DeclarativeContainer):
    config = providers.Configuration(ini_files=['config.ini'])
    db_client = providers.Dependency()
    cache_manager = providers.Dependency()

    # plugins_module's EmailSendService, handed in by the app: it depends on this
    # module, so the dependency cannot point the other way. Password reset mail
    # goes out through the primary email connection.
    email_send_service = providers.Dependency()
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
    user_group_repository = providers.Singleton(
        SQLAlchemyRepository[UserGroup],
        model=UserGroup,
        db_client=db_client,
    )
    user_group_member_repository = providers.Singleton(
        SQLAlchemyRepository[UserGroupMember],
        model=UserGroupMember,
        db_client=db_client,
    )
    user_group_role_repository = providers.Singleton(
        SQLAlchemyRepository[UserGroupRole],
        model=UserGroupRole,
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

    user_service = providers.Singleton(
        UserService,
        user_repository=user_repository,
        user_role_repository=user_role_repository,
        session_repository=session_repository,
        resource_repository=resource_repository,
        cache_manager=cache_manager,
        user_group_member_repository=user_group_member_repository,
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
        cache_manager=cache_manager,
        inactive_days_threshold=config.auth.inactive_days_threshold,
    )

    recaptcha_service = providers.Singleton(
        RecaptchaService,
        enabled=config.recaptcha.enabled,
        project_id=config.recaptcha.project_id,
        site_key=config.recaptcha.site_key,
        score_threshold=config.recaptcha.score_threshold,
    )
