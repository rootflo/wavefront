import os

from dotenv import load_dotenv

load_dotenv()

# Celery broker / backend
CELERY_BROKER_URL: str = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND: str = os.getenv(
    'CELERY_RESULT_BACKEND', 'redis://localhost:6379/1'
)

# Task retry settings
try:
    MAX_RETRIES: int = int(os.getenv('CELERY_TASK_MAX_RETRIES', '0'))
    RETRY_DELAY: int = int(os.getenv('CELERY_TASK_RETRY_DELAY_SECONDS', '30'))
except ValueError as e:
    raise ValueError(f'Invalid integer in retry configuration: {e}') from e

# Redis Stream
STREAM_NAME: str = os.getenv(
    'ASYNC_AGENTIC_EXEC_RESULTS_STREAM', 'async_agentic_exec:results'
)

# Cloud / storage
CLOUD_PROVIDER: str = os.environ['CLOUD_PROVIDER']
CLOUD_REGION: str = os.getenv('CLOUD_REGION', '')
CLOUD_PROJECT_ID: str = os.getenv('CLOUD_PROJECT_ID', '') or os.getenv(
    'GCP_PROJECT_ID', ''
)
CLOUD_LOCATION: str = os.getenv('CLOUD_LOCATION', '')
APPLICATION_BUCKET: str = os.environ.get('APPLICATION_BUCKET') or os.environ.get(
    'AGENT_YAML_BUCKET', ''
)
# Back-compat aliases used as fallbacks while env is migrated
AGENT_YAML_BUCKET: str = APPLICATION_BUCKET or os.environ.get('AGENT_YAML_BUCKET', '')
AGENTIC_EXECUTIONS_BUCKET: str = APPLICATION_BUCKET or os.environ.get(
    'AGENTIC_EXECUTIONS_BUCKET', ''
)
# Queues / KMS (needed when CommonContainer / PluginsContainer resolve cloud clients)
WORKFLOW_QUEUE: str = os.getenv('WORKFLOW_QUEUE', '') or os.getenv(
    'WORKFLOW_WORKER_TOPIC', ''
)
KMS_KEY_RING: str = os.getenv('KMS_KEY_RING', '')
KMS_ENCRYPTION_KEY: str = os.getenv('KMS_ENCRYPTION_KEY', '')
KMS_ENCRYPTION_KEY_VERSION: str = os.getenv('KMS_ENCRYPTION_KEY_VERSION', '')
AZURE_STORAGE_ACCOUNT_URL: str = os.getenv('AZURE_STORAGE_ACCOUNT_URL', '')
AZURE_KEY_VAULT_URL: str = os.getenv('AZURE_KEY_VAULT_URL', '')
AZURE_CLIENT_ID: str = os.getenv('AZURE_CLIENT_ID', '')
AZURE_CLIENT_SECRET: str = os.getenv('AZURE_CLIENT_SECRET', '')
AZURE_TENANT_ID: str = os.getenv('AZURE_TENANT_ID', '')

REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT: str = os.getenv('REDIS_PORT', '6379')
REDIS_PROTOCOL: str = os.getenv('REDIS_PROTOCOL', 'redis')
REDIS_PASSWORD: str = os.getenv('REDIS_PASSWORD', '')
REDIS_DB: str = os.getenv('REDIS_DB', '0')

# App
WORKFLOW_WORKER_TOPIC: str = WORKFLOW_QUEUE
APP_NAME: str = os.getenv('APP_NAME', 'floware')

# Database
DB_USERNAME: str = os.environ['DB_USERNAME']
DB_PASSWORD: str = os.environ['DB_PASSWORD']
DB_HOST: str = os.environ['DB_HOST']
DB_PORT: str = os.environ['DB_PORT']
DB_NAME: str = os.environ['DB_NAME']

# Triggers — Gmail Pub/Sub watch only (OAuth apps live in the DB)
GCP_PROJECT_ID: str = CLOUD_PROJECT_ID
GMAIL_PUBSUB_TOPIC_PREFIX: str = os.getenv(
    'GMAIL_PUBSUB_TOPIC_PREFIX', 'agentic-trigger'
)
GMAIL_PUSH_ENDPOINT_TEMPLATE: str = os.getenv('GMAIL_PUSH_ENDPOINT_TEMPLATE', '')
GMAIL_PUBSUB_OIDC_SA_EMAIL: str = os.getenv('GMAIL_PUBSUB_OIDC_SA_EMAIL', '')
