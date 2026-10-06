ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG = 'ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG'
DATASOURCE_AUDIT_ENABLED_FLAG = 'DATASOURCE_AUDIT_ENABLED_FLAG'
DATASOURCE_CHANGE_NOTIFICATION_FLAG = 'DATASOURCE_CHANGE_NOTIFICATION_FLAG'
INACTIVE_ACCOUNT_DISABLE_FLAG = 'INACTIVE_ACCOUNT_DISABLE_FLAG'
SUPERSET_FLAG = 'SUPERSET_FLAG'

_ALL_FLAGS = (
    ALLOW_NON_ADMIN_ALL_DATA_ACCESS_FLAG,
    DATASOURCE_AUDIT_ENABLED_FLAG,
    DATASOURCE_CHANGE_NOTIFICATION_FLAG,
    INACTIVE_ACCOUNT_DISABLE_FLAG,
    SUPERSET_FLAG,
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
