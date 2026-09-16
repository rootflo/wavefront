"""
Tests for params outside the OpenAI SDK's create() signature.

`chat.completions.create` declares no **kwargs, so a param it does not name -
vLLM's `top_k`, or a server's own sampling knobs - raised TypeError locally and
never reached the server that understands it. `extra_body` is the SDK's own
escape hatch: its contents go into the request body verbatim.
"""

import functools
import inspect
from unittest.mock import AsyncMock, Mock

import pytest
from openai.resources.chat.completions import AsyncCompletions

from flo_ai.llm import AzureOpenAI, OpenAI, OpenAIVLLM
from flo_ai.llm.base_llm import split_request_kwargs


def vllm_llm(**kwargs) -> OpenAIVLLM:
    """Vllm llm."""
    return OpenAIVLLM(
        base_url='http://localhost:8000/v1',
        model='mistral',
        api_key='test-key-123',
        **kwargs,
    )


class TestSplitRequestKwargs:
    """Test cases for splitting against the real SDK signature."""

    def test_declared_params_stay_declared(self):
        """Test declared params stay declared."""
        declared, extra = split_request_kwargs(
            AsyncCompletions.create, {'model': 'm', 'temperature': 0.3, 'top_p': 0.9}
        )

        assert declared == {'model': 'm', 'temperature': 0.3, 'top_p': 0.9}
        assert extra == {}

    def test_undeclared_params_are_separated(self):
        """Test undeclared params are separated."""
        declared, extra = split_request_kwargs(
            AsyncCompletions.create, {'temperature': 0.3, 'top_k': 5}
        )

        assert declared == {'temperature': 0.3}
        assert extra == {'top_k': 5}

    def test_top_k_is_still_not_an_sdk_param(self):
        """If the SDK ever adds it, this indirection stops being needed."""
        params = inspect.signature(AsyncCompletions.create).parameters

        assert (
            'top_k' not in params
        ), 'top_k is now an SDK param; extra_body routing can be revisited'

    def test_a_method_taking_kwargs_needs_no_split(self):
        """A catch-all signature accepts everything, so nothing is diverted."""

        def create(**kwargs):
            """Create."""

        declared, extra = split_request_kwargs(create, {'top_k': 5})

        assert declared == {'top_k': 5}
        assert extra == {}

    def test_a_bound_method_resolves_to_its_function(self):
        """Wrappers pass client.chat.completions.create, which is bound."""
        llm = OpenAI(model='gpt-4o-mini', api_key='test-key-123')

        declared, extra = split_request_kwargs(
            llm.client.chat.completions.create, {'temperature': 0.3, 'top_k': 5}
        )

        assert declared == {'temperature': 0.3}
        assert extra == {'top_k': 5}


class TestCreateKwargs:
    """Test cases for the request params each wrapper builds."""

    def test_vllm_top_k_rides_in_extra_body(self):
        """The config UI offers top_k for vLLM, and vLLM reads it from the body."""
        llm = vllm_llm(top_k=5)

        body = llm._create_kwargs({'model': llm.model, 'messages': [], **llm.kwargs})

        assert 'top_k' not in body
        assert body['extra_body'] == {'top_k': 5}

    def test_declared_params_are_not_diverted(self):
        """Test declared params are not diverted."""
        llm = vllm_llm(top_p=0.9, seed=42)

        body = llm._create_kwargs({'model': llm.model, 'messages': [], **llm.kwargs})

        assert body['top_p'] == 0.9
        assert body['seed'] == 42
        assert 'extra_body' not in body

    def test_a_caller_supplied_extra_body_wins(self):
        """Test a caller supplied extra body wins."""
        llm = vllm_llm(top_k=5)

        body = llm._create_kwargs(
            {
                'model': llm.model,
                'messages': [],
                'extra_body': {'top_k': 9, 'guided_regex': r'\d+'},
                **llm.kwargs,
            }
        )

        assert body['extra_body'] == {'top_k': 9, 'guided_regex': r'\d+'}

    def test_it_takes_a_mapping_so_per_call_params_can_override(self):
        """A key in both the instance and the call is an override, not a clash.

        Passing the merged params as **kwargs made that pair a
        duplicate-argument TypeError at the call itself.
        """
        llm = vllm_llm(top_p=0.9)

        body = llm._create_kwargs(
            {'model': llm.model, 'messages': [], **llm.kwargs, 'top_p': 0.1}
        )

        assert body['top_p'] == 0.1

    def test_azure_diverts_the_same_way(self):
        """Test azure diverts the same way."""
        llm = AzureOpenAI(
            model='gpt-4.1-mini',
            api_key='test-key-123',
            azure_endpoint='https://example.cognitiveservices.azure.com',
            api_version='2024-10-21',
            top_k=5,
        )

        body = llm._create_kwargs({'model': llm.model, 'messages': [], **llm.kwargs})

        assert body['extra_body'] == {'top_k': 5}


class TestRequestBody:
    """Test cases asserting generate() and stream() send the diverted params."""

    @staticmethod
    def _record_create(llm):
        """Replace create() with a recorder that keeps the SDK's signature.

        The body is split against that signature, so a bare AsyncMock - which
        accepts anything - would report a pass-through and prove nothing.
        """
        response = Mock()
        response.choices = [Mock()]
        response.choices[0].message = Mock()
        response.usage = None

        recorder = AsyncMock(return_value=response)

        @functools.wraps(type(llm.client.chat.completions).create)
        async def create(**kwargs):
            """Create."""
            return await recorder(**kwargs)

        llm.client.chat.completions.create = create
        return recorder

    async def test_generate_sends_extra_body(self):
        """Test generate sends extra body."""
        llm = vllm_llm(top_k=5, top_p=0.9)
        create = self._record_create(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}])

        body = create.call_args[1]
        assert body['top_p'] == 0.9
        assert body['extra_body'] == {'top_k': 5}
        assert 'top_k' not in body

    async def test_a_per_call_param_overrides_the_instance(self):
        """Test a per call param overrides the instance."""
        llm = vllm_llm(top_k=5, top_p=0.9)
        create = self._record_create(llm)

        await llm.generate([{'role': 'user', 'content': 'Hello'}], top_p=0.1)

        assert create.call_args[1]['top_p'] == 0.1

    async def test_stream_sends_extra_body(self):
        """Test stream sends extra body."""
        llm = vllm_llm(top_k=5)
        create = self._record_create(llm)

        async def chunks():
            """Chunks."""
            yield Mock(choices=[])

        create.return_value = chunks()

        async for _ in llm.stream([{'role': 'user', 'content': 'Hello'}]):
            pass

        body = create.call_args[1]
        assert body['extra_body'] == {'top_k': 5}


if __name__ == '__main__':
    pytest.main([__file__])
