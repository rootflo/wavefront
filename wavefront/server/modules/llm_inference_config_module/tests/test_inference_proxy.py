import pytest
import uuid
from unittest.mock import AsyncMock, Mock

# from fastapi import Request
# from fastapi.testclient import TestClient
# from httpx import Response as HttpxResponse
from llm_inference_config_module.services.inference_proxy_service import (
    InferenceProxyService,
)
from llm_inference_config_module.models.schemas import InferenceEngineType
from db_repo_module.models.llm_inference_config import LlmInferenceConfig


@pytest.fixture
def mock_llm_inference_config_service():
    return AsyncMock()


@pytest.fixture
def inference_proxy_service(mock_llm_inference_config_service):
    return InferenceProxyService(
        llm_inference_config_service=mock_llm_inference_config_service
    )


@pytest.fixture
def sample_model_config():
    return LlmInferenceConfig(
        id=uuid.uuid4(),
        llm_model='gpt-4',
        display_name='GPT-4',
        api_key='test-api-key',
        type='openai',
        base_url='https://api.openai.com',
        is_deleted=False,
    )


@pytest.mark.asyncio
async def test_get_model_config_success(
    inference_proxy_service, mock_llm_inference_config_service, sample_model_config
):
    """Test successful model config retrieval."""
    model_id = str(sample_model_config.id)
    config_dict = sample_model_config.to_dict(exclude_api_key=False)
    mock_llm_inference_config_service.get_config.return_value = config_dict

    result = await inference_proxy_service.get_model_config(model_id)

    assert str(result.id) == str(sample_model_config.id)
    assert result.llm_model == sample_model_config.llm_model
    assert result.api_key == sample_model_config.api_key
    mock_llm_inference_config_service.get_config.assert_called_once_with(
        sample_model_config.id
    )


@pytest.mark.asyncio
async def test_get_model_config_not_found(
    inference_proxy_service, mock_llm_inference_config_service
):
    """Test model config not found."""
    model_id = str(uuid.uuid4())
    mock_llm_inference_config_service.get_config.return_value = None

    result = await inference_proxy_service.get_model_config(model_id)

    assert result is None


@pytest.mark.asyncio
async def test_get_model_config_invalid_uuid(
    inference_proxy_service, mock_llm_inference_config_service
):
    """Test invalid UUID format."""
    model_id = 'invalid-uuid'

    result = await inference_proxy_service.get_model_config(model_id)

    assert result is None
    mock_llm_inference_config_service.get_config.assert_not_called()


def test_construct_target_url(inference_proxy_service):
    """Test URL construction."""
    base_url = 'https://api.openai.com/'
    model_call_path = '/chat/completions'

    result = inference_proxy_service.construct_target_url(base_url, model_call_path)

    assert result == 'https://api.openai.com/chat/completions'


def test_construct_target_url_no_slashes(inference_proxy_service):
    """Test URL construction without slashes."""
    base_url = 'https://api.openai.com'
    model_call_path = 'chat/completions'

    result = inference_proxy_service.construct_target_url(base_url, model_call_path)

    assert result == 'https://api.openai.com/chat/completions'


def test_prepare_headers_openai(inference_proxy_service):
    """Test header preparation for OpenAI."""
    # Mock request
    request = Mock()
    request.headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'test-agent',
        'Host': 'should-be-excluded',
        'Content-Length': 'should-be-excluded',
    }

    # Mock model config for OpenAI
    model_config = Mock()
    model_config.api_key = 'test-api-key'
    model_config.type = 'openai'

    result = inference_proxy_service.prepare_headers(request, model_config)

    assert result['Content-Type'] == 'application/json'
    assert result['User-Agent'] == 'test-agent'
    assert result['authorization'] == 'Bearer test-api-key'
    assert 'Host' not in result
    assert 'Content-Length' not in result


def test_prepare_headers_gemini(inference_proxy_service):
    """Test header preparation for Gemini."""
    # Mock request
    request = Mock()
    request.headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'test-agent',
        'authorization': 'Bearer should-be-removed',
    }

    # Mock model config for Gemini
    model_config = Mock()
    model_config.api_key = 'test-gemini-key'
    model_config.type = 'gemini'

    result = inference_proxy_service.prepare_headers(request, model_config)

    assert result['Content-Type'] == 'application/json'
    assert result['User-Agent'] == 'test-agent'
    assert result['x-goog-api-key'] == 'test-gemini-key'
    assert 'authorization' not in result  # Should be removed


def test_detect_streaming_openai_true(inference_proxy_service):
    """Test OpenAI streaming detection with stream=true."""
    parsed_data = {'stream': True, 'model': 'gpt-4'}
    model_call_path = '/chat/completions'

    result = inference_proxy_service.detect_streaming(
        InferenceEngineType.OPENAI, parsed_data, model_call_path
    )
    assert result is True


def test_detect_streaming_openai_false(inference_proxy_service):
    """Test OpenAI streaming detection with stream=false."""
    parsed_data = {'stream': False, 'model': 'gpt-4'}
    model_call_path = '/chat/completions'

    result = inference_proxy_service.detect_streaming(
        InferenceEngineType.OPENAI, parsed_data, model_call_path
    )
    assert result is False


def test_detect_streaming_openai_no_stream_key(inference_proxy_service):
    """Test OpenAI streaming detection when stream key is missing."""
    parsed_data = {'model': 'gpt-4'}
    model_call_path = '/chat/completions'

    result = inference_proxy_service.detect_streaming(
        InferenceEngineType.OPENAI, parsed_data, model_call_path
    )
    assert result is False


def test_detect_streaming_gemini_streaming(inference_proxy_service):
    """Test Gemini streaming detection from URL path."""
    parsed_data = {}
    model_call_path = '/v1beta/models/gemini-2.5-flash:streamGenerateContent'

    result = inference_proxy_service.detect_streaming(
        InferenceEngineType.GEMINI, parsed_data, model_call_path
    )
    assert result is True


def test_detect_streaming_gemini_non_streaming(inference_proxy_service):
    """Test Gemini non-streaming detection from URL path."""
    parsed_data = {}
    model_call_path = '/v1beta/models/gemini-2.5-flash:generateContent'

    result = inference_proxy_service.detect_streaming(
        InferenceEngineType.GEMINI, parsed_data, model_call_path
    )
    assert result is False


def test_detect_streaming_fallback_unknown_provider(inference_proxy_service):
    """Test fallback behavior for unknown provider."""
    parsed_data = {'stream': True, 'model': 'test-model'}
    model_call_path = '/some/path'

    # Using a provider type that's not in the mapping (simulate unknown provider)
    result = inference_proxy_service.detect_streaming(
        'unknown_provider', parsed_data, model_call_path
    )
    assert result is True


def test_extract_openai_model(inference_proxy_service):
    """Test OpenAI model extraction from request body."""
    parsed_data = {'model': 'gpt-4', 'stream': False}
    model_call_path = '/chat/completions'

    result = inference_proxy_service._extract_openai_model(parsed_data, model_call_path)
    assert result == 'gpt-4'


def test_extract_gemini_model(inference_proxy_service):
    """Test Gemini model extraction from URL path."""
    parsed_data = {}
    model_call_path = '/v1beta/models/gemini-2.5-flash:generateContent'

    result = inference_proxy_service._extract_gemini_model(parsed_data, model_call_path)
    assert result == 'gemini-2.5-flash'


def test_extract_gemini_model_streaming(inference_proxy_service):
    """Test Gemini model extraction from streaming URL path."""
    parsed_data = {}
    model_call_path = '/v1beta/models/gemini-pro:streamGenerateContent'

    result = inference_proxy_service._extract_gemini_model(parsed_data, model_call_path)
    assert result == 'gemini-pro'


def test_extract_azure_openai_model(inference_proxy_service):
    """Test Azure OpenAI model extraction from URL path."""
    parsed_data = {}
    model_call_path = '/openai/deployments/gpt-4/chat/completions'

    result = inference_proxy_service._extract_azure_openai_model(
        parsed_data, model_call_path
    )
    assert result == 'gpt-4'
