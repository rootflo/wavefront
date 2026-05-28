from enum import Enum


class UserRole(str, Enum):
    OWNER = 'owner'
    APP_ADMIN = 'app_admin'
