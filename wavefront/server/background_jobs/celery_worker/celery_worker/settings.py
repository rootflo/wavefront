"""Load package config.ini once (CWD-independent). Replaces celery_worker.env."""

from pathlib import Path

from dependency_injector import providers
from dotenv import load_dotenv

load_dotenv()

CONFIG_INI = str(Path(__file__).resolve().parent / 'config.ini')

_configuration = providers.Configuration()
_configuration.from_ini(CONFIG_INI)
CONFIG = _configuration()

CELERY_BROKER_URL = CONFIG['celery']['broker_url']
CELERY_RESULT_BACKEND = CONFIG['celery']['result_backend']
MAX_RETRIES = int(CONFIG['celery']['task_max_retries'])
RETRY_DELAY = int(CONFIG['celery']['task_retry_delay_seconds'])
STREAM_NAME = CONFIG['streams']['async_agentic_exec_results']
