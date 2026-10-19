"""OpenAI-protocol providers use tools / tool_calls / role: tool, never role: function."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from flo_ai.agent.agent import Agent
from flo_ai.llm.anthropic_llm import Anthropic
from flo_ai.llm.aws_bedrock_llm import AWSBedrock
from flo_ai.llm.azure_openai_llm import AzureOpenAI
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.llm.openai_vllm import OpenAIVLLM
from flo_ai.tool.base_tool import Tool


def completion(content=None, tool_calls=None):
    message = SimpleNamespace(
        content=content, tool_calls=tool_calls, function_call=None
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def tool_call(call_id='call_1', name='lookup', arguments='{"query": "x"}'):
    return SimpleNamespace(
        id=call_id,
        type='function',
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def make_llm(kind):
    if kind == 'openai':
        llm = OpenAI(model='gpt-5.4', api_key='key')
    elif kind == 'azure':
        llm = AzureOpenAI(
            model='gpt-5.4', api_key='key', azure_endpoint='https://example.azure.com'
        )
    else:
        llm = OpenAIVLLM(model='m', api_key='key', base_url='http://vllm')
    llm.client = Mock()
    llm.client.chat.completions.create = AsyncMock(return_value=completion('ok'))
    return llm


def lookup_tool():
    async def lookup(query: str) -> str:
        return f'result for {query}'

    return Tool(
        name='lookup',
        description='Look something up',
        function=lookup,
        parameters={'query': {'type': 'string', 'description': 'What to look up'}},
    )


LLM_KINDS = ['openai', 'azure', 'vllm']


@pytest.mark.parametrize('kind', LLM_KINDS)
def test_format_tool_wraps_function(kind):
    formatted = make_llm(kind).format_tool_for_llm(lookup_tool())
    assert formatted['type'] == 'function'
    assert formatted['function']['name'] == 'lookup'
    assert formatted['function']['parameters']['required'] == ['query']


@pytest.mark.parametrize('kind', ['openai', 'azure'])
@pytest.mark.asyncio
async def test_generate_sends_tools_not_functions(kind):
    llm = make_llm(kind)
    tools = llm.format_tools_for_llm([lookup_tool()])
    await llm.generate([{'role': 'user', 'content': 'hi'}], functions=tools)

    kwargs = llm.client.chat.completions.create.call_args[1]
    assert kwargs['tools'] == tools
    assert 'functions' not in kwargs
    assert 'function_call' not in kwargs


@pytest.mark.parametrize('kind', ['openai', 'azure'])
@pytest.mark.asyncio
async def test_generate_wraps_legacy_function_specs(kind):
    llm = make_llm(kind)
    spec = {'name': 'lookup', 'parameters': {'type': 'object', 'properties': {}}}
    await llm.generate([{'role': 'user', 'content': 'hi'}], functions=[spec])

    kwargs = llm.client.chat.completions.create.call_args[1]
    assert kwargs['tools'] == [{'type': 'function', 'function': spec}]


@pytest.mark.parametrize('kind', LLM_KINDS)
@pytest.mark.asyncio
async def test_legacy_function_messages_are_rewritten(kind):
    llm = make_llm(kind)
    messages = [
        {'role': 'user', 'content': 'hi'},
        {'role': 'function', 'name': 'lookup', 'content': 'earlier result'},
    ]
    await llm.generate(messages)

    sent = llm.client.chat.completions.create.call_args[1]['messages']
    assert [m['role'] for m in sent] == ['user', 'assistant', 'tool']
    call = sent[1]['tool_calls'][0]
    assert call['function']['name'] == 'lookup'
    assert sent[2] == {
        'role': 'tool',
        'tool_call_id': call['id'],
        'content': 'earlier result',
    }
    assert messages[1]['role'] == 'function'


@pytest.mark.parametrize('kind', LLM_KINDS)
@pytest.mark.asyncio
async def test_tool_call_round_trip_messages(kind):
    llm = make_llm(kind)
    response = completion(content=None, tool_calls=[tool_call()]).choices[0].message

    function_call = await llm.get_function_call(response)
    assert function_call == {
        'name': 'lookup',
        'arguments': '{"query": "x"}',
        'id': 'call_1',
    }
    assert llm.get_tool_use_id(function_call) == 'call_1'
    assert llm.format_tool_call_message(response, function_call) == {
        'role': 'assistant',
        'content': None,
        'tool_calls': [
            {
                'id': 'call_1',
                'type': 'function',
                'function': {'name': 'lookup', 'arguments': '{"query": "x"}'},
            }
        ],
    }
    assert llm.format_function_result_message('lookup', 'done', 'call_1') == {
        'role': 'tool',
        'tool_call_id': 'call_1',
        'content': 'done',
    }


@pytest.mark.asyncio
async def test_get_function_call_from_dict_and_no_tool_calls():
    llm = make_llm('openai')
    call = {
        'id': 'call_9',
        'type': 'function',
        'function': {'name': 'lookup', 'arguments': '{}'},
    }
    assert await llm.get_function_call({'tool_calls': [call]}) == {
        'name': 'lookup',
        'arguments': '{}',
        'id': 'call_9',
    }
    assert await llm.get_function_call(completion('plain').choices[0].message) is None


def test_other_providers_keep_their_result_format():
    anthropic = Anthropic(model='claude', api_key='key')
    assert anthropic.format_function_result_message('lookup', 'r', 'tu_1')['role'] == (
        'function'
    )
    assert anthropic.format_tool_call_message(Mock(), {'id': 'tu_1'}) is None

    bedrock = AWSBedrock.__new__(AWSBedrock)
    assert (
        bedrock.format_function_result_message('lookup', 'r', 'tu_1')['role'] == 'tool'
    )


@pytest.mark.parametrize('kind', ['openai', 'azure'])
@pytest.mark.asyncio
async def test_agent_tool_loop_sends_tool_messages(kind):
    llm = make_llm(kind)
    replies = [completion(tool_calls=[tool_call(arguments=json.dumps({'query': 'x'}))])]
    llm.client.chat.completions.create = AsyncMock(
        side_effect=lambda **_: replies.pop(0)
        if replies
        else completion('final answer')
    )
    agent = Agent(
        name='tester', system_prompt='Use tools.', llm=llm, tools=[lookup_tool()]
    )

    await agent.run('look up x')

    calls = llm.client.chat.completions.create.call_args_list
    assert len(calls) >= 2
    sent = calls[1][1]['messages']
    assert all(m['role'] != 'function' for m in sent)
    assistant = next(m for m in sent if m.get('tool_calls'))
    assert assistant['role'] == 'assistant'
    assert assistant['tool_calls'][0]['id'] == 'call_1'
    result = sent[sent.index(assistant) + 1]
    assert result == {
        'role': 'tool',
        'tool_call_id': 'call_1',
        'content': 'result for x',
    }
