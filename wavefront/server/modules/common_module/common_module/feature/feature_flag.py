import os

AZURE_FLAG = 'AZURE_FLAG'
AZURE_OPENAI_FLAG = 'AZURE_OPENAI_FLAG'
CELERY_FLAG = 'CELERY_FLAG'
EMAIL_SYNC_FLAG = 'EMAIL_SYNC_FLAG'
GOOGLE_FLAG = 'GOOGLE_FLAG'
INACTIVE_ACCOUNT_DISABLE_FLAG = 'INACTIVE_ACCOUNT_DISABLE_FLAG'
SAML_FLAG = 'SAML_FLAG'
SLACK_FLAG = 'SLACK_FLAG'
SUPERSET_FLAG = 'SUPERSET_FLAG'
VECTOR_DB_FLAG = 'VECTOR_DB_FLAG'

feature_flag_config = {
    AZURE_FLAG: os.environ.get(AZURE_FLAG, 'false'),
    AZURE_OPENAI_FLAG: os.environ.get(AZURE_OPENAI_FLAG, 'false'),
    CELERY_FLAG: os.environ.get(CELERY_FLAG, 'false'),
    EMAIL_SYNC_FLAG: os.environ.get(EMAIL_SYNC_FLAG, 'false'),
    GOOGLE_FLAG: os.environ.get(GOOGLE_FLAG, 'false'),
    INACTIVE_ACCOUNT_DISABLE_FLAG: os.environ.get(
        INACTIVE_ACCOUNT_DISABLE_FLAG, 'false'
    ),
    SAML_FLAG: os.environ.get(SAML_FLAG, 'false'),
    SLACK_FLAG: os.environ.get(SLACK_FLAG, 'false'),
    SUPERSET_FLAG: os.environ.get(SUPERSET_FLAG, 'false'),
    VECTOR_DB_FLAG: os.environ.get(VECTOR_DB_FLAG, 'false'),
}


def is_feature_enabled(feature: str):
    return feature_flag_config[feature] == 'true'
