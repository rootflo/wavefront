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


def test_guardrails_reads_spacy_model_settings(monkeypatch):
    # The worker registers Presidio only when it can resolve a spaCy model, and
    # the image ships none: without these keys PII policies fail closed here.
    from common_module.config_loader import load_ini
    from dependency_injector import providers

    monkeypatch.setenv(
        'GUARDRAILS_SPACY_MODEL_URL', 'https://example.test/model.tar.gz'
    )
    monkeypatch.setenv('GUARDRAILS_MODEL_CACHE_DIR', '/models/spacy')
    configuration = providers.Configuration(strict=True)
    load_ini(configuration, settings.CONFIG_INI)

    guardrails = configuration()['guardrails']
    assert guardrails['spacy_model_url'] == 'https://example.test/model.tar.gz'
    assert guardrails['model_cache_dir'] == '/models/spacy'


def test_config_has_no_kms_or_encryption_flag():
    # Only floware decrypts secrets; the worker reads plaintext from it.
    assert 'kms_encryption' not in settings.CONFIG
    assert 'feature_flags' not in settings.CONFIG
