"""Unit tests for guardrails engine factory and controller responses."""

from unittest.mock import MagicMock, patch
import pytest
from guardrails_module.services.engine_factory import build_guardrails_engine
from guardrails_module.controllers.guardrails_controller import list_supported_adapters


def test_build_guardrails_engine_disabled():
    mock_resolver = MagicMock()
    engine = build_guardrails_engine(mock_resolver, guardrails_enabled=False)
    assert engine is not None
    assert engine.registered == ()


def test_build_guardrails_engine_enabled_with_presidio():
    mock_resolver = MagicMock()
    with patch(
        'guardrails_module.services.model_loader.is_spacy_model_available',
        return_value=True,
    ), patch(
        'guardrails_module.services.model_loader.ensure_spacy_model',
        return_value='/tmp/models/cached_spacy',
    ), patch('flo_ai.guardrails.adapters.PresidioAdapter') as mock_adapter_cls:
        mock_instance = MagicMock()
        mock_instance.name = 'presidio_pii'
        mock_adapter_cls.return_value = mock_instance

        engine = build_guardrails_engine(
            mock_resolver,
            guardrails_enabled=True,
            spacy_model_url='https://models.example.com/model.tar.gz',
            model_cache_dir='/tmp/models',
        )
        assert engine is not None
        mock_adapter_cls.assert_called_once_with(
            model='/tmp/models/cached_spacy',
        )
        assert 'presidio_pii' in engine.registered


def test_build_guardrails_engine_enabled_without_spacy_url():
    mock_resolver = MagicMock()
    with patch(
        'guardrails_module.services.model_loader.is_spacy_model_available',
        return_value=False,
    ):
        engine = build_guardrails_engine(
            mock_resolver,
            guardrails_enabled=True,
            spacy_model_url=None,
        )
        assert engine is not None
        assert 'presidio_pii' not in engine.registered


def test_build_guardrails_engine_enabled_with_preinstalled_spacy_package():
    mock_resolver = MagicMock()
    with patch(
        'guardrails_module.services.model_loader.is_spacy_model_available',
        return_value=True,
    ), patch(
        'guardrails_module.services.model_loader.ensure_spacy_model',
        return_value='en_core_web_lg',
    ), patch('flo_ai.guardrails.adapters.PresidioAdapter') as mock_adapter_cls:
        mock_instance = MagicMock()
        mock_instance.name = 'presidio_pii'
        mock_adapter_cls.return_value = mock_instance

        engine = build_guardrails_engine(
            mock_resolver,
            guardrails_enabled=True,
            spacy_model_url=None,
        )
        assert engine is not None
        assert 'presidio_pii' in engine.registered
        mock_adapter_cls.assert_called_once_with(
            model='en_core_web_lg',
        )


@pytest.mark.asyncio
async def test_list_supported_adapters_disabled():
    mock_request = MagicMock()
    mock_engine = MagicMock()
    mock_engine.registered = ()
    mock_formatter = MagicMock()
    mock_formatter.buildSuccessResponse.side_effect = lambda data: {'data': data}

    with patch(
        'guardrails_module.controllers.guardrails_controller._require_admin',
        return_value=None,
    ):
        response = await list_supported_adapters(
            request=mock_request,
            guardrails_engine=mock_engine,
            response_formatter=mock_formatter,
            config={'guardrails': {'enabled': 'false'}},
        )
        import json

        data = json.loads(response.body)
        assert data['data']['enabled'] is False
        assert data['data']['adapters'] == []
        assert data['data']['unavailable'] == []


@pytest.mark.asyncio
async def test_list_supported_adapters_enabled():
    mock_request = MagicMock()
    mock_engine = MagicMock()
    mock_engine.registered = ('presidio_pii',)
    mock_formatter = MagicMock()
    mock_formatter.buildSuccessResponse.side_effect = lambda data: {'data': data}

    with patch(
        'guardrails_module.controllers.guardrails_controller._require_admin',
        return_value=None,
    ):
        response = await list_supported_adapters(
            request=mock_request,
            guardrails_engine=mock_engine,
            response_formatter=mock_formatter,
            config={'guardrails': {'enabled': 'true'}},
        )
        import json

        data = json.loads(response.body)
        assert data['data']['enabled'] is True
        assert data['data']['adapters'] == ['presidio_pii']
        assert 'azure_content_safety' in data['data']['unavailable']


@pytest.mark.asyncio
async def test_list_supported_adapters_enabled_without_adapters():
    mock_request = MagicMock()
    mock_engine = MagicMock()
    mock_engine.registered = ()
    mock_formatter = MagicMock()
    mock_formatter.buildSuccessResponse.side_effect = lambda data: {'data': data}

    with patch(
        'guardrails_module.controllers.guardrails_controller._require_admin',
        return_value=None,
    ):
        response = await list_supported_adapters(
            request=mock_request,
            guardrails_engine=mock_engine,
            response_formatter=mock_formatter,
            config={'guardrails': {'enabled': 'true'}},
        )
        import json

        data = json.loads(response.body)
        assert data['data']['enabled'] is True
        assert data['data']['adapters'] == []
        assert set(data['data']['unavailable']) == {
            'presidio_pii',
            'azure_content_safety',
        }


def test_build_guardrails_engine_raises_when_model_download_fails():
    mock_resolver = MagicMock()
    with patch(
        'guardrails_module.services.model_loader.is_spacy_model_available',
        return_value=True,
    ), patch(
        'guardrails_module.services.model_loader.ensure_spacy_model',
        side_effect=RuntimeError('download failed'),
    ), pytest.raises(RuntimeError, match='download failed'):
        build_guardrails_engine(
            mock_resolver,
            guardrails_enabled=True,
            spacy_model_url='https://models.example.com/model.tar.gz',
        )
