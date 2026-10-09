"""Load package config.ini once (CWD-independent). Replaces celery_worker.env."""

from pathlib import Path

from common_module.config_loader import load_ini
from dependency_injector import providers
from dotenv import load_dotenv

_PACKAGE = Path(__file__).resolve().parent
load_dotenv(_PACKAGE / '.env')

CONFIG_INI = _PACKAGE / 'config.ini'

_configuration = providers.Configuration(strict=True)
load_ini(_configuration, CONFIG_INI)
CONFIG = _configuration()

CELERY_BROKER_URL = CONFIG['celery']['broker_url']
CELERY_RESULT_BACKEND = CONFIG['celery']['result_backend']
MAX_RETRIES = int(CONFIG['celery']['task_max_retries'])
RETRY_DELAY = int(CONFIG['celery']['task_retry_delay_seconds'])
STREAM_NAME = CONFIG['streams']['async_agentic_exec_results']
