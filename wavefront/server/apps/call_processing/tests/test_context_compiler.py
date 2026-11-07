import asyncio
import json
import logging

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext

from call_processing.services.common.context import compiler
from call_processing.services.common.context.compiler import start_prefetch
from call_processing.services.common.context.store import CallContextStore
from call_processing.services.common.context.subject import CallSubject
from call_processing.services.common.tools.tool_wrapper_service import (
    ApiToolWrapper,
    ToolWrapperFactory,
)

from tests.test_call_context_store import FakeRedis

SUBJECT = CallSubject('CA123', 'inbound', '+911234567890')


def _tool(context=None, method='GET', name='find_account', enabled=True):
    association = {'is_enabled': enabled}
    if context is not None:
        association['config_overrides'] = {'context': context}
    return {
        'name': name,
        'description': 'Find the account',
        'tool_type': 'api',
        'config': {'url': 'https://water.test/account', 'method': method},
        'parameter_schema': {
            'properties': {'mobile_number': {'type': 'string'}},
            'required': ['mobile_number'],
        },
        'association': association,
    }


PREFETCH = {'bind': {'mobile_number': 'caller.phone'}, 'prefetch': True}


@pytest.fixture
def api_calls(monkeypatch):
    calls = []

    async def fake_execute(self, params):
        calls.append(dict(params))
        return {'name': 'Jane Doe'}

    monkeypatch.setattr(ApiToolWrapper, 'execute', fake_execute)
    return calls


async def _drain():
    await asyncio.gather(*list(compiler._background))


def _ai_tool(tools, store):
    _, registrations = ToolWrapperFactory.create_all_tool_functions(
        tools, call_subject=SUBJECT, agent_id='agent-1', context_store=store
    )
    return dict(registrations)


async def test_prefetched_result_is_served_to_the_ais_call(api_calls):
    store = CallContextStore(FakeRedis())
    tools = [_tool(PREFETCH)]

    assert start_prefetch(tools, SUBJECT, 'agent-1', store) == 1
    await _drain()
    result = await _ai_tool(tools, store)['find_account']({})

    assert result == {'name': 'Jane Doe'}
    assert api_calls == [{'mobile_number': '+911234567890'}]


async def test_a_second_start_does_not_fetch_again(api_calls):
    store = CallContextStore(FakeRedis())
    tools = [_tool(PREFETCH)]

    start_prefetch(tools, SUBJECT, 'agent-1', store)  # Twilio webhook
    start_prefetch(tools, SUBJECT, 'agent-1', store)  # stream connects
    await _drain()

    assert len(api_calls) == 1


@pytest.mark.parametrize(
    'tool',
    [
        _tool(PREFETCH, method='POST'),  # writes are never prefetched
        _tool({'prefetch': True}),  # the AI would send other arguments
        _tool(PREFETCH, enabled=False),
        _tool({**PREFETCH, 'bind': {'mobile_number': 'caller.email'}}),
        _tool({'bind': {'mobile_number': 'caller.phone'}}),  # not opted in
    ],
)
async def test_tools_that_cannot_prefetch_are_skipped(api_calls, tool):
    store = CallContextStore(FakeRedis())

    assert start_prefetch([tool], SUBJECT, 'agent-1', store) == 0
    await _drain()
    assert api_calls == []


async def test_post_tool_marked_read_only_can_prefetch(api_calls):
    store = CallContextStore(FakeRedis())
    tool = _tool({**PREFETCH, 'read_only': True}, method='POST')

    assert start_prefetch([tool], SUBJECT, 'agent-1', store) == 1
    await _drain()
    assert len(api_calls) == 1


async def test_read_only_tool_repeat_lookup_fetches_once(api_calls):
    store = CallContextStore(FakeRedis())
    fn = _ai_tool([_tool({'read_only': True})], store)['find_account']

    await fn({'mobile_number': '+911234567890'})
    await fn({'mobile_number': '+911234567890'})

    assert len(api_calls) == 1


async def test_tool_without_context_settings_is_never_cached(api_calls):
    store = CallContextStore(FakeRedis())
    fn = _ai_tool([_tool()], store)['find_account']

    await fn({'mobile_number': '+911234567890'})
    await fn({'mobile_number': '+911234567890'})

    assert len(api_calls) == 2


async def test_prefetch_logs_call_info_with_secret_headers_redacted(api_calls, caplog):
    store = CallContextStore(FakeRedis())
    tool = _tool(PREFETCH)
    tool['config'].update(
        headers={'X-Tenant': 'riverbend', 'X-Api-Token': 'abc'},
        auth_type='bearer',
        auth_credentials={'token': 'secret-token'},
    )

    with caplog.at_level(logging.INFO, logger='call_processing'):
        start_prefetch([tool], SUBJECT, 'agent-1', store)
        await _drain()

    done = next(
        r.getMessage() for r in caplog.records if 'Prefetch done' in r.getMessage()
    )
    assert "tool 'find_account', call CA123 (inbound), agent agent-1" in done
    assert 'fetched GET https://water.test/account in' in done
    assert "'X-Tenant': 'riverbend'" in done
    assert "'Authorization': '<redacted>'" in done
    assert "'X-Api-Token': '<redacted>'" in done
    assert 'secret-token' not in caplog.text
    assert '1234567890' not in caplog.text
    lookup_key = next(
        r.getMessage().split('key ')[1]
        for r in caplog.records
        if 'Call context miss, called the API and saved' in r.getMessage()
    )
    assert done.endswith(f'key {lookup_key}')


def test_log_safe_headers_redacts_secrets():
    wrapper = ApiToolWrapper(
        url='https://water.test',
        method='GET',
        headers={'X-Tenant': 'riverbend', 'X-Api-Token': 'abc', 'X-Client': 'c1'},
        auth_type='api_key',
        auth_credentials={'key_name': 'X-Client', 'key_value': 'k1'},
    )

    assert wrapper.log_safe_headers() == {
        'X-Tenant': 'riverbend',
        'X-Api-Token': '<redacted>',
        'X-Client': '<redacted>',
    }


class _Params:
    """What Pipecat hands a tool function: arguments, call id and the LLM context."""

    def __init__(self, arguments, tool_call_id, context=None):
        self.arguments = arguments
        self.tool_call_id = tool_call_id
        self.context = context if context is not None else LLMContext()
        self.sent = []

    async def result_callback(self, result, properties=None):
        self.sent.append(result)
        # As Pipecat's aggregator does once the result frame reaches it
        self.context.add_message(
            {
                'role': 'tool',
                'tool_call_id': self.tool_call_id,
                'content': json.dumps(result),
            }
        )


async def test_ai_call_after_prefetch_logs_a_hit_with_the_same_key(api_calls, caplog):
    store = CallContextStore(FakeRedis())
    tools = [_tool(PREFETCH)]

    with caplog.at_level(logging.INFO, logger='call_processing'):
        start_prefetch(tools, SUBJECT, 'agent-1', store)
        await _drain()
        await _ai_tool(tools, store)['find_account']({})

    messages = [r.getMessage() for r in caplog.records]
    miss = next(m for m in messages if 'Call context miss' in m)
    hit = next(m for m in messages if 'Call context hit' in m)
    assert 'API call skipped (saved result from Redis)' in hit
    assert hit.split('key ')[1] == miss.split('key ')[1]
    assert len(api_calls) == 1


async def test_repeated_identical_result_is_sent_as_a_short_reference(api_calls):
    store = CallContextStore(FakeRedis())
    fn = _ai_tool([_tool({'read_only': True})], store)['find_account']
    context = LLMContext()
    first = _Params({'mobile_number': '+911234567890'}, 'call_1', context)
    second = _Params({'mobile_number': '+911234567890'}, 'call_2', context)

    await fn(first)
    await fn(second)

    assert first.sent == [{'name': 'Jane Doe'}]
    assert second.sent == [
        {
            'unchanged': True,
            'same_as_tool_call_id': 'call_1',
            'note': 'Same result as the earlier find_account call in this '
            'conversation. Answer from that result.',
        }
    ]
    assert len(api_calls) == 1


async def test_different_arguments_still_get_the_full_result(api_calls):
    store = CallContextStore(FakeRedis())
    fn = _ai_tool([_tool({'read_only': True})], store)['find_account']
    other = _Params({'mobile_number': '+910000000000'}, 'call_2')

    await fn(_Params({'mobile_number': '+911234567890'}, 'call_1'))
    await fn(other)

    assert other.sent == [{'name': 'Jane Doe'}]
    assert len(api_calls) == 2


@pytest.mark.parametrize('earlier', ['CANCELLED', 'IN_PROGRESS', None])
async def test_a_result_the_ai_never_got_is_sent_in_full(api_calls, earlier):
    store = CallContextStore(FakeRedis())
    fn = _ai_tool([_tool({'read_only': True})], store)['find_account']
    context = LLMContext()
    first = _Params({'mobile_number': '+911234567890'}, 'call_1', LLMContext())
    await fn(first)
    if earlier is not None:
        # Interrupted before the result landed; None: trimmed from the context
        context.add_message(
            {'role': 'tool', 'tool_call_id': 'call_1', 'content': earlier}
        )
    second = _Params({'mobile_number': '+911234567890'}, 'call_2', context)

    await fn(second)

    assert second.sent == [{'name': 'Jane Doe'}]


def _write_tool():
    return {**_tool(method='POST', name='record_payment'), 'description': 'Pay'}


async def test_reads_after_a_write_fetch_current_data_then_reuse_it(api_calls):
    store = CallContextStore(FakeRedis())
    fns = _ai_tool([_tool({'read_only': True}), _write_tool()], store)
    context = LLMContext()
    args = {'mobile_number': '+911234567890'}

    await fns['find_account'](_Params(args, 'call_1', context))
    await fns['record_payment'](_Params(args, 'call_2', context))
    after_write = _Params(args, 'call_3', context)
    await fns['find_account'](after_write)
    again = _Params(args, 'call_4', context)
    await fns['find_account'](again)

    # read, write, a fresh read; the repeat after it reuses the fresh one
    assert len(api_calls) == 3
    assert after_write.sent == [{'name': 'Jane Doe'}]
    assert again.sent[0]['same_as_tool_call_id'] == 'call_3'


async def test_lowercase_method_override_still_prefetches(api_calls):
    tool = _tool(PREFETCH, method='POST')
    tool['association']['config_overrides']['method'] = 'get'

    store = CallContextStore(FakeRedis())

    assert start_prefetch([tool], SUBJECT, 'agent-1', store) == 1
    await _drain()
    assert len(api_calls) == 1
