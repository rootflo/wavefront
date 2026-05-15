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
AGENT_YAML_BUCKET: str = os.environ['AGENT_YAML_BUCKET']
AGENTIC_EXECUTIONS_BUCKET: str = os.environ['AGENTIC_EXECUTIONS_BUCKET']

# App
WORKFLOW_WORKER_TOPIC: str = os.getenv('WORKFLOW_WORKER_TOPIC', '')
APP_NAME: str = os.getenv('APP_NAME', 'floware')

# Database
DB_USERNAME: str = os.environ['DB_USERNAME']
DB_PASSWORD: str = os.environ['DB_PASSWORD']
DB_HOST: str = os.environ['DB_HOST']
DB_PORT: str = os.environ['DB_PORT']
DB_NAME: str = os.environ['DB_NAME']
