import asyncio

import pytest

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
