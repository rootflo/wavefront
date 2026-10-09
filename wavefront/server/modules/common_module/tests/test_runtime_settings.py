"""RuntimeSettings.from_config."""

import pytest

from common_module.runtime_settings import RuntimeSettings
from common_module.runtime_settings import RuntimeSettingsError


def _complete(**overrides):
    config = {
        'env_config': {
            'app_env': 'dev',
            'base_url': 'http://floware:8001/',
            'passthrough_secret': 's3cret',
            'worker_count': '2',
            'uvicorn_log_level': 'info',
        },
        'web': {'allowed_origins': 'http://a.test, http://b.test'},
        'voice_agents': {'call_processing_base_url': 'http://calls:8003'},
    }
    return config


def test_from_config_reads_all_sections():
    settings = RuntimeSettings.from_config(_complete())

    assert settings == RuntimeSettings(
        app_env='dev',
        floware_base_url='http://floware:8001',
        passthrough_secret='s3cret',
        call_processing_base_url='http://calls:8003',
        allowed_origins=('http://a.test', 'http://b.test'),
        worker_count=2,
        uvicorn_log_level='info',
    )


def test_optional_values_are_absent_when_empty():
    config = _complete()
    config['env_config']['passthrough_secret'] = ''
    config['voice_agents']['call_processing_base_url'] = ''

    settings = RuntimeSettings.from_config(config)

    assert settings.passthrough_secret is None
    assert settings.call_processing_base_url is None


def test_missing_required_value_raises():
    config = _complete()
    config['env_config']['app_env'] = ''

    with pytest.raises(RuntimeSettingsError):
        RuntimeSettings.from_config(config)


def test_settings_are_immutable():
    settings = RuntimeSettings.from_config(_complete())
    with pytest.raises(AttributeError):
        settings.app_env = 'dev'  # type: ignore[misc]
