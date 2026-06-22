from typing import Annotated, Any

from auth_module.auth_container import AuthContainer
from auth_module.services.token_service import TokenService
from common_module.common_cache import CommonCache
from common_module.common_container import CommonContainer
from common_module.response_formatter import ResponseFormatter
from db_repo_module.cache.cache_manager import CacheManager
from db_repo_module.models.resource import Resource
from db_repo_module.models.role import Role
from db_repo_module.models.role_resource import RoleResource
from db_repo_module.models.user import User
from db_repo_module.models.user_role import UserRole
from db_repo_module.repositories.sql_alchemy_repository import SQLAlchemyRepository
from dependency_injector.wiring import Provide
from fastapi import Depends

from user_management_module.services.account_lockout_service import (
    AccountLockoutService,
)
from user_management_module.services.email_service import EmailService
from user_management_module.services.user_service import UserService
from user_management_module.user_container import UserContainer

ResponseFormatterDep = Annotated[
    ResponseFormatter, Depends(Provide[CommonContainer.response_formatter])
]
UserRepositoryDep = Annotated[
    SQLAlchemyRepository[User], Depends(Provide[UserContainer.user_repository])
]
UserRoleRepositoryDep = Annotated[
    SQLAlchemyRepository[UserRole],
    Depends(Provide[UserContainer.user_role_repository]),
]
ResourceRepositoryDep = Annotated[
    SQLAlchemyRepository[Resource],
    Depends(Provide[UserContainer.resource_repository]),
]
RoleRepositoryDep = Annotated[
    SQLAlchemyRepository[Role], Depends(Provide[UserContainer.role_repository])
]
RoleResourceRepositoryDep = Annotated[
    SQLAlchemyRepository[RoleResource],
    Depends(Provide[UserContainer.role_resource_repository]),
]
UserServiceDep = Annotated[UserService, Depends(Provide[UserContainer.user_service])]
CacheManagerDep = Annotated[CacheManager, Depends(Provide[UserContainer.cache_manager])]
CommonCacheDep = Annotated[CommonCache, Depends(Provide[CommonContainer.cache_manager])]
TokenServiceDep = Annotated[TokenService, Depends(Provide[AuthContainer.token_service])]
EmailServiceDep = Annotated[EmailService, Depends(Provide[UserContainer.email_service])]
AccountLockoutServiceDep = Annotated[
    AccountLockoutService,
    Depends(Provide[UserContainer.account_lockout_service]),
]
UserConfigDep = Annotated[dict[str, Any], Depends(Provide[UserContainer.config])]
