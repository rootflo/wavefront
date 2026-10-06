ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG = 'ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG'
AZURE_FLAG = 'AZURE_FLAG'
AZURE_OPENAI_FLAG = 'AZURE_OPENAI_FLAG'
CELERY_FLAG = 'CELERY_FLAG'
DATASOURCE_AUDIT_ENABLED_FLAG = 'DATASOURCE_AUDIT_ENABLED_FLAG'
DATASOURCE_CHANGE_NOTIFICATION_FLAG = 'DATASOURCE_CHANGE_NOTIFICATION_FLAG'
EMAIL_SYNC_FLAG = 'EMAIL_SYNC_FLAG'
GOOGLE_FLAG = 'GOOGLE_FLAG'
INACTIVE_ACCOUNT_DISABLE_FLAG = 'INACTIVE_ACCOUNT_DISABLE_FLAG'
SAML_FLAG = 'SAML_FLAG'
SLACK_FLAG = 'SLACK_FLAG'
SUPERSET_FLAG = 'SUPERSET_FLAG'
VECTOR_DB_FLAG = 'VECTOR_DB_FLAG'

_ALL_FLAGS = (
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG,
    AZURE_FLAG,
    AZURE_OPENAI_FLAG,
    CELERY_FLAG,
    DATASOURCE_AUDIT_ENABLED_FLAG,
    DATASOURCE_CHANGE_NOTIFICATION_FLAG,
    EMAIL_SYNC_FLAG,
    GOOGLE_FLAG,
    INACTIVE_ACCOUNT_DISABLE_FLAG,
    SAML_FLAG,
    SLACK_FLAG,
    SUPERSET_FLAG,
    VECTOR_DB_FLAG,
)

feature_flag_config = {name: 'false' for name in _ALL_FLAGS}


def configure_feature_flags(**values: str) -> None:
    """Apply ``[feature_flags]`` from an app's config.ini at startup.

    Config parsers may lowercase section keys; names are matched case-insensitively
    against the known flag constants.
    """
    for name, value in values.items():
        key = name.upper()
        if key in feature_flag_config and value is not None and value != '':
            feature_flag_config[key] = value


def is_feature_enabled(feature: str):
    return feature_flag_config[feature] == 'true'
