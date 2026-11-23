"""
Tests for rate-limit stalling and provider error typing at the LLM boundary.

A 429 used to reach BaseAgent.handle_error, which sent the error and the whole
conversation back to the same rate-limited LLM for "analysis", wrote the reply
into the conversation history, and retried at once.
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp

import anthropic
import botocore.exceptions
import httpx
import openai
import pytest
from google.genai import errors as genai_errors

from flo_ai.agent.agent import Agent
from flo_ai.agent.builder import AgentBuilder
from flo_ai.arium.llm_router import SmartRouter
from flo_ai.arium.memory import MessageMemory, MessageMemoryItem
from flo_ai.llm import rate_limit
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.guarded_llm import GuardedLLM
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.llm.rate_limit import (
    LLMProviderError,
    LLMRateLimited,
    RateLimitGate,
    classify,
    rate_limited,
    rate_limited_stream,
)
from flo_ai.llm.rootflo_llm import RootFloLLM
from flo_ai.models.chat_message import FunctionMessage, UserMessage
from flo_ai.tool.base_tool import Tool, ToolExecutionError

router_module = sys.modules[SmartRouter.__module__]

REQUEST = httpx.Request('POST', 'https://api.example.invalid/v1/chat')


def response(status, headers=None):
    return httpx.Response(status, headers=headers or {}, request=REQUEST)


def openai_429(retry_after=None, code='rate_limit_exceeded'):
    headers = {'retry-after': str(retry_after)} if retry_after is not None else {}
    return openai.RateLimitError(
        'rate limited', response=response(429, headers), body={'code': code}
    )


def openai_500():
    return openai.InternalServerError('server error', response=response(500), body=None)


def openai_400():
    return openai.BadRequestError('bad request', response=response(400), body=None)


def completion(content=None, tool_calls=None):
    message = SimpleNamespace(
        content=content, tool_calls=tool_calls, function_call=None
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def openai_401():
    return openai.AuthenticationError('bad key', response=response(401), body=None)


def gemini_429(details):
    return genai_errors.ClientError(
        429,
        {
            'error': {
                'code': 429,
                'status': 'RESOURCE_EXHAUSTED',
                'message': 'quota',
                'details': details,
            }
        },
    )


class FakeTime:
    """Clock and sleep for a gate, so stalls take no real time."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def clock(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ScriptedLLM(BaseLLM):
    """Returns or raises each scripted item in turn."""

    def __init__(self, script, model='fake-model', api_key='key'):
        super().__init__(model=model, api_key=api_key)
        self.script = list(script)
        self.calls = 0

    @rate_limited(provider='fake')
    async def generate(self, messages, functions=None, output_schema=None, **kwargs):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return {'content': item}

    @rate_limited_stream(provider='fake')
    async def stream(self, messages, functions=None, output_schema=None, **kwargs):
        self.calls += 1
        chunks, error = self.script.pop(0)
        for chunk in chunks:
            yield {'content': chunk}
        if error is not None:
            raise error

    def get_message_content(self, response):
        return response['content']

    def format_tool_for_llm(self, tool):
        return {'tool': tool}

    def format_tools_for_llm(self, tools):
        return [{'tool': t} for t in tools]

    def format_image_in_message(self, image):
        return {'image': image}


@pytest.fixture(autouse=True)
def fresh_gates(monkeypatch):
    monkeypatch.setattr(rate_limit, '_gates', {})


@pytest.fixture
def fake_time():
    return FakeTime()


def install_gate(llm, fake_time):
    gate = RateLimitGate(
        clock=fake_time.clock, sleep=fake_time.sleep, rand=lambda a, b: 0.0
    )
    rate_limit._gates[llm.rate_limit_scope()] = gate
    return gate


class TestClassify:
    def test_openai_429_reads_retry_after(self):
        info = classify(openai_429(retry_after=2))
        assert (info.kind, info.status, info.retry_after) == ('rate_limit', 429, 2.0)

    def test_retry_after_ms_wins(self):
        error = openai.RateLimitError(
            'x',
            response=response(429, {'retry-after-ms': '1500', 'retry-after': '9'}),
            body=None,
        )
        assert classify(error).retry_after == 1.5

    def test_insufficient_quota_is_fatal(self):
        assert classify(openai_429(code='insufficient_quota')).kind == 'fatal'

    def test_anthropic_429_and_overloaded(self):
        limited = anthropic.RateLimitError('x', response=response(429), body=None)
        overloaded = anthropic.APIStatusError('x', response=response(529), body=None)
        assert classify(limited).kind == 'rate_limit'
        assert classify(overloaded).kind == 'rate_limit'

    def test_wrapped_error_is_found_through_cause(self):
        try:
            try:
                raise anthropic.RateLimitError('x', response=response(429), body=None)
            except Exception as e:
                raise Exception(f'Error in Claude API call: {e}') from e
        except Exception as wrapped:
            assert classify(wrapped).kind == 'rate_limit'

    def test_gemini_nested_retry_delay(self):
        error = gemini_429(
            [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '3s'}]
        )
        info = classify(error)
        assert (info.kind, info.retry_after) == ('rate_limit', 3.0)

    def test_gemini_daily_quota_is_fatal(self):
        error = gemini_429(
            [
                {
                    '@type': 'type.googleapis.com/google.rpc.QuotaFailure',
                    'violations': [
                        {'quotaId': 'GenerateRequestsPerDayPerProjectPerModel'}
                    ],
                }
            ]
        )
        assert classify(error).kind == 'fatal'

    def test_bedrock_throttling(self):
        error = botocore.exceptions.ClientError(
            {
                'Error': {'Code': 'ThrottlingException', 'Message': 'slow down'},
                'ResponseMetadata': {'HTTPStatusCode': 400},
            },
            'InvokeModel',
        )
        assert classify(error).kind == 'rate_limit'

    def test_transient_and_fatal(self):
        assert classify(openai_500()).kind == 'transient'
        assert classify(openai.APIConnectionError(request=REQUEST)).kind == 'transient'
        assert classify(openai_401()).kind == 'fatal'

    def test_ollama_body_reaches_the_typed_error(self):
        error = aiohttp.ClientResponseError(
            Mock(real_url='http://ollama.invalid/api/generate'),
            (),
            status=404,
            message="model 'llama3' not found",
        )
        typed = LLMProviderError(f'ollama request failed: {error}')
        assert classify(error).kind == 'fatal'
        assert "model 'llama3' not found" in str(typed)

    def test_unrelated_error_is_not_classified(self):
        assert classify(ValueError('bug')) is None


class TestRateLimitedGenerate:
    async def test_stalls_then_succeeds(self, fake_time):
        llm = ScriptedLLM([openai_429(2), openai_429(3), 'ok'])
        install_gate(llm, fake_time)

        result = await llm.generate([])

        assert result == {'content': 'ok'}
        assert llm.calls == 3
        assert fake_time.sleeps == [2.0, 3.0]

    async def test_backoff_without_retry_after_still_pauses(self, fake_time):
        llm = ScriptedLLM([openai_429(), 'ok'])
        install_gate(llm, fake_time)

        await llm.generate([])

        # Equal jitter with rand=0 is half the 1s ceiling, never ~0.
        assert fake_time.sleeps == [0.5]

    async def test_budget_exhausted_raises(self, fake_time):
        llm = ScriptedLLM([openai_429(40), openai_429(40), 'ok'])
        llm.rate_limit_max_wait = 60
        install_gate(llm, fake_time)

        with pytest.raises(LLMRateLimited) as caught:
            await llm.generate([])

        assert llm.calls == 2
        assert fake_time.sleeps == [40.0]
        assert isinstance(caught.value.__cause__, openai.RateLimitError)

    async def test_zero_budget_never_retries(self, fake_time):
        llm = ScriptedLLM([openai_429(1), 'ok'])
        llm.rate_limit_max_wait = 0
        install_gate(llm, fake_time)

        with pytest.raises(LLMRateLimited):
            await llm.generate([])

        assert llm.calls == 1
        assert fake_time.sleeps == []

    async def test_other_errors_are_typed(self, fake_time):
        llm = ScriptedLLM([openai_500(), openai_401()])
        install_gate(llm, fake_time)

        with pytest.raises(LLMProviderError) as transient:
            await llm.generate([])
        with pytest.raises(LLMProviderError) as fatal:
            await llm.generate([])

        assert transient.value.transient and transient.value.status == 500
        assert not fatal.value.transient
        assert not isinstance(fatal.value, LLMRateLimited)

    async def test_unrelated_error_propagates_untouched(self, fake_time):
        llm = ScriptedLLM([ValueError('bug')])
        install_gate(llm, fake_time)

        with pytest.raises(ValueError):
            await llm.generate([])


class TestSharedGate:
    async def test_429_pauses_other_callers_on_same_scope(self, fake_time):
        first = ScriptedLLM([openai_429(5)])
        first.rate_limit_max_wait = 0
        second = ScriptedLLM(['ok'])
        other_model = ScriptedLLM(['ok'], model='other-model')
        install_gate(first, fake_time)
        install_gate(other_model, fake_time)

        with pytest.raises(LLMRateLimited):
            await first.generate([])
        await other_model.generate([])
        assert fake_time.sleeps == []

        await second.generate([])
        assert fake_time.sleeps == [5.0]

    async def test_cooldown_beyond_budget_fails_without_sleeping(self, fake_time):
        llm = ScriptedLLM(['ok'])
        llm.rate_limit_max_wait = 10
        gate = install_gate(llm, fake_time)
        gate.extend(90)

        with pytest.raises(LLMRateLimited):
            await llm.generate([])

        assert llm.calls == 0
        assert fake_time.sleeps == []

    def test_proxy_and_direct_api_do_not_share_a_gate(self):
        direct = OpenAI(model='gpt-4o', api_key='sk-same')
        proxied = OpenAI(
            model='gpt-4o', api_key='sk-same', base_url='https://proxy.invalid/v1'
        )
        assert direct.rate_limit_scope() != proxied.rate_limit_scope()


class TestRateLimitedStream:
    async def test_retries_before_first_chunk(self, fake_time):
        llm = ScriptedLLM([([], openai_429(1)), (['a', 'b'], None)])
        install_gate(llm, fake_time)

        chunks = [chunk['content'] async for chunk in llm.stream([])]

        assert chunks == ['a', 'b']
        assert fake_time.sleeps == [1.0]

    async def test_raises_after_first_chunk(self, fake_time):
        llm = ScriptedLLM([(['a'], openai_429(1)), (['b'], None)])
        install_gate(llm, fake_time)

        chunks = []
        with pytest.raises(LLMRateLimited):
            async for chunk in llm.stream([]):
                chunks.append(chunk['content'])

        assert chunks == ['a']
        assert llm.calls == 1
        # Other callers on the scope still back off.
        assert rate_limit._gates[llm.rate_limit_scope()].remaining() > 0


class TestSettingReachesTheProvider:
    def test_builder_does_not_leak_into_request_params(self):
        llm = OpenAI(model='gpt-4o', api_key='sk-test')
        agent = AgentBuilder().with_llm(llm).with_rate_limit_wait(5).build()

        assert agent.llm.rate_limit_max_wait == 5
        assert 'rate_limit_max_wait' not in agent.llm.kwargs
        assert 'rate_limit_max_wait' not in agent.llm._create_kwargs(
            dict(agent.llm.kwargs)
        )

    def test_builder_does_not_mutate_a_shared_llm(self):
        shared = ScriptedLLM([])
        agent = AgentBuilder().with_llm(shared).with_rate_limit_wait(5).build()

        assert agent.llm is not shared
        assert agent.llm.rate_limit_max_wait == 5
        assert shared.rate_limit_max_wait == rate_limit.DEFAULT_RATE_LIMIT_MAX_WAIT

    def test_guarded_llm_mirrors_both_ways(self):
        inner = ScriptedLLM([])
        inner.rate_limit_max_wait = 30
        guarded = GuardedLLM(inner, engine=None)

        assert guarded.rate_limit_max_wait == 30
        guarded.rate_limit_max_wait = 12
        assert inner.rate_limit_max_wait == 12

    async def test_rootflo_hands_value_and_scope_to_wrapper(self):
        llm = RootFloLLM(base_url='https://example.invalid', model_id='model-1')
        llm.rate_limit_max_wait = 7
        llm._fetch_llm_config_async = AsyncMock(
            return_value={'llm_model': 'gpt-4.1-mini', 'type': 'openai'}
        )

        await llm._ensure_initialized()

        assert llm._llm.rate_limit_max_wait == 7
        assert llm._llm.rate_limit_scope() == (
            'rootflo',
            'https://example.invalid',
            'model-1',
        )
        llm.rate_limit_max_wait = 3
        assert llm._llm.rate_limit_max_wait == 3


@pytest.fixture
def no_retry_sleep(monkeypatch):
    monkeypatch.setattr('flo_ai.agent.agent.provider_retry_sleep', AsyncMock())


class TestAgent:
    async def test_rate_limit_skips_analysis_and_rolls_back(self, fake_time):
        llm = ScriptedLLM([openai_429(1), 'analysis that must not be requested'])
        llm.rate_limit_max_wait = 0
        install_gate(llm, fake_time)
        agent = Agent(name='a', system_prompt='be helpful', llm=llm, max_retries=3)

        with pytest.raises(LLMRateLimited):
            await agent.run('hello')

        assert llm.calls == 1
        assert agent.conversation_history == []

    async def test_transient_error_retries_without_analysis(
        self, fake_time, no_retry_sleep
    ):
        llm = ScriptedLLM([openai_500(), 'answer'])
        install_gate(llm, fake_time)
        agent = Agent(name='a', system_prompt='be helpful', llm=llm, max_retries=3)

        history = await agent.run('hello')

        assert llm.calls == 2
        assert history[-1].content == 'answer'
        assert not any('Error occurred' in str(m.content) for m in history)

    async def test_transient_retries_exhausted_raise_and_roll_back(
        self, fake_time, no_retry_sleep
    ):
        llm = ScriptedLLM([openai_500(), openai_500()])
        install_gate(llm, fake_time)
        agent = Agent(name='a', system_prompt='be helpful', llm=llm, max_retries=1)

        with pytest.raises(LLMProviderError) as caught:
            await agent.run('hello')

        assert caught.value.transient
        assert llm.calls == 2
        assert agent.conversation_history == []

    async def test_tool_http_error_still_gets_analysis(self):
        llm = ScriptedLLM(['try a different argument'])
        agent = Agent(name='a', system_prompt='be helpful', llm=llm)
        try:
            try:
                raise httpx.ConnectError('tool backend down', request=REQUEST)
            except Exception as e:
                # As Tool.execute raises it: inside the except, without `from`.
                raise ToolExecutionError(f'Error executing tool t: {e}')
        except ToolExecutionError as tool_error:
            should_retry, analysis = await agent.handle_error(tool_error, {})

        assert llm.calls == 1
        assert should_retry and analysis == 'try a different argument'

    async def test_failed_classifier_keeps_the_answer(self, fake_time):
        for error in (openai_500(), openai_401(), openai_429(1)):
            llm = ScriptedLLM([error])
            llm.rate_limit_max_wait = 0
            install_gate(llm, fake_time)
            agent = Agent(name='a', system_prompt='x', llm=llm)

            assert await agent._is_final_answer('The answer is 4.', 1, []) is True

    async def test_tool_result_survives_a_later_provider_error(self):
        sent_emails = []

        async def send_email(to: str) -> str:
            sent_emails.append(to)
            return 'sent'

        tool = Tool(
            name='send_email',
            description='Send an email',
            function=send_email,
            parameters={'to': {'type': 'string', 'description': 'Recipient'}},
        )
        call = SimpleNamespace(
            id='call_1',
            type='function',
            function=SimpleNamespace(
                name='send_email', arguments=json.dumps({'to': 'a@b.c'})
            ),
        )
        replies = [completion(tool_calls=[call]), openai_400()]

        async def create(**_):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply

        llm = OpenAI(model='gpt-4o', api_key='key')
        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(side_effect=create)
        agent = Agent(name='a', system_prompt='x', llm=llm, tools=[tool])

        with pytest.raises(LLMProviderError):
            await agent.run('email a@b.c')

        assert sent_emails == ['a@b.c']
        assert any(isinstance(m, FunctionMessage) for m in agent.conversation_history)


class TestSchemaInstruction:
    async def test_retry_does_not_repeat_the_instruction(self, fake_time):
        llm = OpenAI(model='gpt-4o', api_key='key')
        llm.client = Mock()
        llm.client.chat.completions.create = AsyncMock(
            side_effect=[openai_429(1), completion('{}')]
        )
        install_gate(llm, fake_time)
        messages = [{'role': 'system', 'content': 'be helpful'}]

        await llm.generate(messages, output_schema={'title': 's', 'type': 'object'})

        sent = llm.client.chat.completions.create.call_args_list[1][1]['messages']
        assert sent[0]['content'].count('Please provide your response in JSON') == 1
        assert messages == [{'role': 'system', 'content': 'be helpful'}]


class TestRouter:
    async def test_fatal_provider_error_is_not_a_fallback_route(self, fake_time):
        llm = ScriptedLLM([openai_401()])
        install_gate(llm, fake_time)
        router = SmartRouter({'researcher': 'r', 'analyst': 'a'}, llm=llm)
        memory = MessageMemory()
        memory.add(MessageMemoryItem(node='user', result=UserMessage('hi')))

        with pytest.raises(LLMProviderError):
            await router.route(memory)

    async def test_exhausted_transient_errors_raise(self, fake_time, monkeypatch):
        monkeypatch.setattr(router_module, 'provider_retry_sleep', AsyncMock())
        llm = ScriptedLLM([openai_500(), openai_500(), openai_500()])
        install_gate(llm, fake_time)
        router = SmartRouter({'researcher': 'r', 'analyst': 'a'}, llm=llm)
        memory = MessageMemory()
        memory.add(MessageMemoryItem(node='user', result=UserMessage('hi')))

        with pytest.raises(LLMProviderError) as caught:
            await router.route(memory)

        assert caught.value.transient
        assert llm.calls == 3


class TestRootFloConfigFetch:
    """The proxy's config fetch runs outside the decorated inner LLM."""

    @pytest.fixture
    def proxy(self, monkeypatch):
        """Route RootFloLLM's httpx client to a handler; returns the request log."""
        state = {'handler': None, 'requests': []}
        real_client = httpx.AsyncClient

        def handle(request):
            state['requests'].append(request)
            return state['handler'](request)

        monkeypatch.setattr(
            'flo_ai.llm.rootflo_llm.httpx.AsyncClient',
            lambda: real_client(transport=httpx.MockTransport(handle)),
        )
        return state

    def build(self):
        return RootFloLLM(base_url='https://proxy.invalid', model_id='model-1')

    async def test_401_is_a_fatal_provider_error(self, proxy):
        proxy['handler'] = lambda request: httpx.Response(401, text='bad token')

        with pytest.raises(LLMProviderError) as caught:
            await self.build().generate([])

        assert caught.value.status == 401
        assert not caught.value.transient

    async def test_connection_failure_is_transient(self, proxy):
        def refuse(request):
            raise httpx.ConnectError('refused', request=request)

        proxy['handler'] = refuse

        with pytest.raises(LLMProviderError) as caught:
            await self.build().generate([])

        assert caught.value.transient

    async def test_agent_does_not_analyse_a_failed_fetch(self, proxy):
        proxy['handler'] = lambda request: httpx.Response(401, text='bad token')
        agent = Agent(
            name='a', system_prompt='be helpful', llm=self.build(), max_retries=3
        )

        with pytest.raises(LLMProviderError):
            await agent.run('hello')

        # An analysis call would have re-fetched the config.
        assert len(proxy['requests']) == 1
        assert agent.conversation_history == []
