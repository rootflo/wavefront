from enum import Enum


class AppStatus(str, Enum):
    SUCCESS = 'success'
    IN_PROGRESS = 'in_progress'
    FAILED = 'failed'


class AppDeploymentType(str, Enum):
    MANUAL = 'manual'
    AUTO = 'auto'
