"""RuntimeSettings.from_config."""

import pytest

from common_module.runtime_settings import RuntimeSettings


def test_from_config_reads_all_sections():
    settings = RuntimeSettings.from_config(
        {
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
    )

    assert settings == RuntimeSettings(
        app_env='dev',
        floware_base_url='http://floware:8001',
        passthrough_secret='s3cret',
        call_processing_base_url='http://calls:8003',
        allowed_origins=('http://a.test', 'http://b.test'),
        worker_count=2,
        uvicorn_log_level='info',
    )


def test_from_config_empty_values_fall_back_to_defaults():
    settings = RuntimeSettings.from_config(
        {'env_config': {'app_env': '', 'base_url': '', 'passthrough_secret': ''}}
    )

    assert settings == RuntimeSettings()
    assert settings.app_env == 'production'
    assert settings.passthrough_secret is None


def test_settings_are_immutable():
    with pytest.raises(AttributeError):
        RuntimeSettings().app_env = 'dev'  # type: ignore[misc]
