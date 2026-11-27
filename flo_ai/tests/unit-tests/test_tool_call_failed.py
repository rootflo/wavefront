"""ToolCallFailed: the tool could not do its job. The agent counts the call as
failed and hands the model the reason as the result, without error analysis or
retry. Tool and PartialTool pass it through instead of wrapping it."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import flo_ai.agent.agent as agent_module
from flo_ai.agent.agent import Agent
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.tool.base_tool import Tool, ToolCallFailed
from flo_ai.tool.partial_tool import PartialTool


def completion(content=None, tool_calls=None):
    message = SimpleNamespace(
        content=content, tool_calls=tool_calls, function_call=None
    )
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def failing_tool():
    async def insert(table: str) -> str:
        raise ToolCallFailed('Insert failed (500): boom')

    return Tool(
        name='insert',
        description='Insert a row',
        function=insert,
        parameters={'table': {'type': 'string', 'description': 'Target table'}},
    )


@pytest.mark.asyncio
async def test_agent_reports_the_failure_to_the_model(monkeypatch):
    llm = OpenAI(model='gpt-5.4', api_key='key')
    llm.client = Mock()
    call = SimpleNamespace(
        id='call_1',
        type='function',
        function=SimpleNamespace(name='insert', arguments=json.dumps({'table': 't'})),
    )
    replies = [completion(tool_calls=[call])]
    llm.client.chat.completions.create = AsyncMock(
        side_effect=lambda **_: replies.pop(0)
        if replies
        else completion('final answer')
    )
    record = Mock()
    monkeypatch.setattr(agent_module.agent_metrics, 'record_tool_call', record)
    agent = Agent(
        name='tester', system_prompt='Use tools.', llm=llm, tools=[failing_tool()]
    )
    agent.handle_error = AsyncMock()

    await agent.run('insert a row')

    sent = llm.client.chat.completions.create.call_args_list[1][1]['messages']
    assert {
        'role': 'tool',
        'tool_call_id': 'call_1',
        'content': 'Insert failed (500): boom',
    } in sent
    record.assert_called_once_with('tester', 'insert', 'error')
    agent.handle_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_tool_execute_does_not_wrap_it():
    with pytest.raises(ToolCallFailed, match='boom'):
        await failing_tool().execute(table='t')


@pytest.mark.asyncio
async def test_partial_tool_does_not_wrap_it():
    partial = PartialTool(failing_tool(), prefilled_params={'table': 't'})

    with pytest.raises(ToolCallFailed, match='boom'):
        await partial.execute()
