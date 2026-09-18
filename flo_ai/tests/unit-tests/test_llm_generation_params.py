"""
Pytest tests for forwarding generation params (top_p, seed, penalties, token
limits) from a wrapper's constructor through to the provider's request.
"""

import inspect
from unittest.mock import AsyncMock, Mock

import pytest
from anthropic import AsyncAnthropic
from openai import AsyncAzureOpenAI, AsyncOpenAI

from flo_ai.llm import Anthropic, AzureOpenAI, Gemini, OpenAI, OpenAIVLLM
from flo_ai.llm.base_llm import split_client_kwargs


def azure_llm(**kwargs) -> AzureOpenAI:
    """Azure llm."""
    return AzureOpenAI(
        model='gpt-4.1-mini',
        api_key='test-key-123',
        azure_endpoint='https://example.cognitiveservices.azure.com',
        api_version='2024-10-21',
        **kwargs,
    )


class TestSplitClientKwargs:
    """Test cases for splitting client options from generation params."""

    def test_generation_params_go_to_the_request(self):
        """Test generation params go to the request."""
        client_kwargs, request_kwargs = split_client_kwargs(
            AsyncOpenAI, {'top_p': 0.9, 'seed': 42}
        )

        assert client_kwargs == {}
        assert request_kwargs == {'top_p': 0.9, 'seed': 42}

    def test_client_options_go_to_the_client(self):
        """Test client options go to the client."""
        client_kwargs, request_kwargs = split_client_kwargs(
            AsyncOpenAI, {'timeout': 30, 'max_retries': 2, 'top_p': 0.9}
        )

        assert client_kwargs == {'timeout': 30, 'max_retries': 2}
        assert request_kwargs == {'top_p': 0.9}

    def test_reserved_names_are_dropped(self):
        """Passing them again would be a duplicate keyword argument."""
        client_kwargs, request_kwargs = split_client_kwargs(
            AsyncAnthropic,
            {'default_headers': {'x': '1'}, 'top_p': 0.9},
            reserved=('default_headers',),
        )

        assert client_kwargs == {}
        assert request_kwargs == {'top_p': 0.9}

    def test_no_generation_param_is_shadowed_by_a_client_option(self):
        """The split routes by name, so an overlap would misroute silently.

        Mirrors the params the config UI collects (client/src/config/
        llm-providers.ts). An SDK release adding one of these as a client
        option must fail here rather than quietly stop sending it.
        """
        ui_params = {
            'temperature',
            'max_tokens',
            'max_completion_tokens',
            'top_p',
            'top_k',
            'frequency_penalty',
            'presence_penalty',
            'seed',
            'service_tier',
        }

        for client_cls in (AsyncOpenAI, AsyncAzureOpenAI, AsyncAnthropic):
            shadowed = ui_params & set(
                inspect.signature(client_cls.__init__).parameters
            )
            assert not shadowed, f'{client_cls.__name__} shadows {shadowed}'


class TestConstructorsAcceptGenerationParams:
    """The SDK clients declare no **kwargs, so a stray param raises TypeError."""

    def test_openai(self):
        """Test openai."""
        llm = OpenAI(
            model='gpt-4o-mini',
            api_key='test-key-123',
            temperature=0.3,
            top_p=0.9,
            seed=42,
            max_completion_tokens=100,
            frequency_penalty=0.5,
            presence_penalty=0.25,
            service_tier='auto',
        )

        assert llm.temperature == 0.3
        assert llm.kwargs == {
            'top_p': 0.9,
            'seed': 42,
            'max_completion_tokens': 100,
            'frequency_penalty': 0.5,
            'presence_penalty': 0.25,
            'service_tier': 'auto',
        }

    def test_azure_openai(self):
        """Test azure openai."""
        llm = azure_llm(temperature=0.3, top_p=0.9, seed=42, frequency_penalty=0.5)

        assert llm.temperature == 0.3
        assert llm.kwargs == {'top_p': 0.9, 'seed': 42, 'frequency_penalty': 0.5}

    def test_anthropic(self):
        """Test anthropic."""
        llm = Anthropic(
            model='claude-3-5-sonnet-20240620',
            api_key='test-key-123',
            temperature=0.3,
            top_p=0.9,
            top_k=5,
            max_tokens=100,
        )

        assert llm.kwargs == {'top_p': 0.9, 'top_k': 5, 'max_tokens': 100}

    def test_openai_vllm(self):
        """Test openai vllm."""
        llm = OpenAIVLLM(
            base_url='http://localhost:8000/v1',
            model='mistral',
            api_key='test-key-123',
            temperature=0.3,
            top_p=0.9,
            presence_penalty=0.25,
        )

        assert llm.kwargs == {'top_p': 0.9, 'presence_penalty': 0.25}

    def test_client_options_still_configure_the_client(self):
        """Test client options still configure the client."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123', max_retries=7)

        assert llm.client.max_retries == 7
        assert 'max_retries' not in llm.kwargs

    def test_no_extra_params_leaves_kwargs_empty(self):
        """Test no extra params leaves kwargs empty."""
        assert OpenAI(api_key='test-key-123').kwargs == {}


class TestGenerationParamsReachTheRequestBody:
    """Test cases asserting the params land in the outgoing payload."""

    @staticmethod
    def _mock_client(llm):
        """Mock client."""
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.choices[0].message.content = 'Hello, world!'
        response.usage = None

        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(return_value=response)
        return llm.client.chat.completions.create

    async def test_openai_body(self):
        """Test openai body."""
        llm = OpenAI(
            model='gpt-4o-mini',
            api_key='test-key-123',
            temperature=0.3,
            top_p=0.9,
            seed=42,
        )
        create = self._mock_client(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}])

        body = create.call_args[1]
        assert body['temperature'] == 0.3
        assert body['top_p'] == 0.9
        assert body['seed'] == 42

    async def test_azure_openai_body(self):
        """Test azure openai body."""
        llm = azure_llm(temperature=0.3, top_p=0.9, seed=42)
        create = self._mock_client(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}])

        body = create.call_args[1]
        assert body['temperature'] == 0.3
        assert body['top_p'] == 0.9
        assert body['seed'] == 42

    async def test_per_call_params_override_the_instance(self):
        """Test per call params override the instance."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123', top_p=0.9)
        create = self._mock_client(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}], top_p=0.1)

        assert create.call_args[1]['top_p'] == 0.1


class TestGeminiGenerationParams:
    """Gemini's config object rejects unknown fields and renames token limits."""

    def _llm(self, **kwargs) -> Gemini:
        """Llm."""
        return Gemini(model='gemini-2.5-flash', api_key='test-key-123', **kwargs)

    def test_max_tokens_is_mapped_to_max_output_tokens(self):
        """Test max tokens is mapped to max output tokens."""
        llm = self._llm(temperature=0.3, max_tokens=100, top_p=0.9)

        assert llm._generation_config_kwargs({}) == {
            'max_output_tokens': 100,
            'top_p': 0.9,
        }

    def test_unsupported_param_is_skipped_not_raised(self):
        """service_tier is an OpenAI-only setting; it must not fail the call."""
        llm = self._llm(service_tier='auto', top_p=0.9)

        assert llm._generation_config_kwargs({}) == {'top_p': 0.9}

    def test_shared_params_pass_through(self):
        """Test shared params pass through."""
        llm = self._llm(top_k=5, seed=42, frequency_penalty=0.5)

        assert llm._generation_config_kwargs({}) == {
            'top_k': 5,
            'seed': 42,
            'frequency_penalty': 0.5,
        }

    def test_per_call_params_override_the_instance(self):
        """Test per call params override the instance."""
        llm = self._llm(top_p=0.9)

        assert llm._generation_config_kwargs({'top_p': 0.1}) == {'top_p': 0.1}

    @staticmethod
    def _mock_generate(llm):
        """generate_content runs via asyncio.to_thread, so mock it as sync."""
        response = Mock()
        response.usage_metadata = None
        response.candidates = []
        response.text = 'Hello, world!'

        llm.client = Mock()
        llm.client.models.generate_content = Mock(return_value=response)
        return llm.client.models.generate_content

    @staticmethod
    def _mock_stream(llm):
        """Stream chunk."""
        chunk = Mock()
        chunk.text = 'Hello, world!'

        llm.client = Mock()
        llm.client.models.generate_content_stream = Mock(return_value=iter([chunk]))
        return llm.client.models.generate_content_stream

    async def test_generate_accepts_a_per_call_temperature(self):
        """Regression: temperature is a config field, so it arrived twice."""
        llm = self._llm(temperature=0.3)
        generate_content = self._mock_generate(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}], temperature=0.1)

        assert generate_content.call_args[1]['config'].temperature == 0.1

    async def test_generate_falls_back_to_the_instance_temperature(self):
        """Test generate falls back to the instance temperature."""
        llm = self._llm(temperature=0.3)
        generate_content = self._mock_generate(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}])

        assert generate_content.call_args[1]['config'].temperature == 0.3

    async def test_stream_accepts_a_per_call_temperature(self):
        """Regression: stream propagated the duplicate-argument TypeError."""
        llm = self._llm(temperature=0.3)
        stream = self._mock_stream(llm)

        async for _ in llm.stream(
            [{'role': 'user', 'content': 'Hello'}], temperature=0.1
        ):
            pass

        assert stream.call_args[1]['config'].temperature == 0.1

    async def test_stream_falls_back_to_the_instance_temperature(self):
        """Test stream falls back to the instance temperature."""
        llm = self._llm(temperature=0.3)
        stream = self._mock_stream(llm)

        async for _ in llm.stream([{'role': 'user', 'content': 'Hello'}]):
            pass

        assert stream.call_args[1]['config'].temperature == 0.3


@pytest.mark.parametrize(
    'factory',
    [
        lambda: OpenAI(api_key='k', top_p=0.9),
        lambda: azure_llm(top_p=0.9),
        lambda: Anthropic(api_key='k', top_p=0.9),
        lambda: OpenAIVLLM(
            base_url='http://localhost:8000/v1', model='m', api_key='k', top_p=0.9
        ),
    ],
    ids=['openai', 'azure_openai', 'anthropic', 'vllm'],
)
def test_constructing_with_a_generation_param_does_not_raise(factory):
    """Regression: these params used to be handed to the SDK client."""
    assert factory().kwargs == {'top_p': 0.9}
