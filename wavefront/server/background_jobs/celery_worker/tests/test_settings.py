"""Package config loads from the package directory, not CWD."""

from pathlib import Path

from celery_worker import settings


def test_config_ini_is_next_to_settings_module():
    assert Path(settings.CONFIG_INI).name == 'config.ini'
    assert Path(settings.CONFIG_INI).parent == Path(settings.__file__).resolve().parent
    assert Path(settings.CONFIG_INI).is_file()


def test_config_exposes_celery_and_stream_settings():
    assert 'celery' in settings.CONFIG
    assert 'streams' in settings.CONFIG
    assert settings.CELERY_BROKER_URL
    assert settings.CELERY_RESULT_BACKEND
    assert settings.STREAM_NAME
    assert isinstance(settings.MAX_RETRIES, int)
    assert isinstance(settings.RETRY_DELAY, int)
