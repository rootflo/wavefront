"""Tests for chat-session behaviour: angle brackets in conversation text, and
interactive agents that hand the turn back to the person."""

import pytest

from flo_ai.agent import Agent, AgentBuilder, AgentEventType, ReasoningPattern
from flo_ai.arium import AriumBuilder
from flo_ai.models import (
    AssistantMessage,
    FunctionMessage,
    TextMessageContent,
    ToolCall,
    UserMessage,
)
from flo_ai.tool import Tool

from test_plan_execute import ScriptedLLM, call, plan, text


def lookup_tool(result='looked up'):
    async def lookup(query: str) -> str:
        return result

    return Tool(
        name='lookup',
        description='Look something up',
        function=lookup,
        parameters={'query': {'type': 'string', 'description': 'What to look up'}},
    )


def contents(request):
    return [m['content'] for m in request]


class TestAngleBracketsInConversation:
    """Text already in the conversation is sent as stored, never as a template."""

    async def test_a_reply_with_angle_brackets_does_not_break_the_next_turn(self):
        llm = ScriptedLLM([text('Name it <workflow_name>.'), text('Sure.')])
        agent = Agent('a', 'sys', llm)

        await agent.run('how should I name it?')
        history = await agent.run('thanks')

        assert history[-1].content == 'Sure.'
        assert 'Name it <workflow_name>.' in contents(llm.requests[1])

    async def test_a_tool_result_with_angle_brackets_is_fine(self):
        llm = ScriptedLLM(
            [
                call('lookup', query='x'),
                text('Done'),
                text('FINAL'),
                text('Yes.'),
                text('FINAL'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[lookup_tool('<html><body>hi</body>')])

        await agent.run('fetch the page')
        history = await agent.run('did it work?')

        assert history[-1].content == 'Yes.'

    async def test_another_agents_output_with_angle_brackets_is_fine(self):
        first = Agent('first', 'one', ScriptedLLM([text('Use a <div> here.')]))
        second_llm = ScriptedLLM([text('ok')])
        second = Agent('second', 'two', second_llm)
        arium = (
            AriumBuilder()
            .add_agents([first, second])
            .start_with(first)
            .connect(first, second)
            .end_with(second)
            .build()
        )

        result = await arium.run('go')

        assert result[-1].result.content == 'ok'
        assert 'Use a <div> here.' in contents(second_llm.requests[0])

    async def test_a_stored_conversation_with_angle_brackets_can_be_replayed(self):
        stored = [
            UserMessage(content='make a workflow'),
            AssistantMessage(
                content='Calling <create>.',
                tool_calls=[ToolCall(name='lookup', arguments={'query': '<q>'})],
            ),
            FunctionMessage(content='<result>ok</result>', name='lookup'),
            AssistantMessage(content='Created <workflow_name>.'),
        ]
        llm = ScriptedLLM([text('It is fine.'), text('FINAL')])
        agent = Agent('a', 'Help <user_name>.', llm, tools=[lookup_tool()])

        history = await agent.run(
            [*stored, UserMessage(content=TextMessageContent(text='is it ok?'))],
            variables={'user_name': 'Priya'},
        )

        assert history[-1].content == 'It is fine.'
        assert llm.requests[0][0]['content'] == 'Help Priya.'
        # The tool call and its result were left exactly as stored.
        assert stored[1].content == 'Calling <create>.'
        assert stored[2].content == '<result>ok</result>'

    async def test_a_variable_value_with_angle_brackets_is_not_resolved_again(self):
        llm = ScriptedLLM([text('ok')])
        agent = Agent('a', 'Wrap answers in <tag>.', llm)

        await agent.run('hi', variables={'tag': '<b>'})

        assert llm.requests[0][0]['content'] == 'Wrap answers in <b>.'


class TestTemplatedInputsStillWork:
    """Outside interactive use, a run's own inputs are still templates."""

    async def test_string_input_is_filled_in(self):
        llm = ScriptedLLM([text('ok')])
        agent = Agent('a', 'sys', llm)

        await agent.run('Summarise <topic>.', variables={'topic': 'tides'})

        assert contents(llm.requests[0])[-1] == 'Summarise tides.'

    async def test_message_inputs_are_filled_in(self):
        llm = ScriptedLLM([text('ok')])
        agent = Agent('a', 'sys', llm)

        await agent.run(
            [
                UserMessage(content='About <topic>.'),
                UserMessage(content=TextMessageContent(text='In <language>.')),
            ],
            variables={'topic': 'tides', 'language': 'French'},
        )

        assert contents(llm.requests[0])[1:] == ['About tides.', 'In French.']

    async def test_a_missing_variable_in_a_string_input_is_still_an_error(self):
        agent = Agent('a', 'sys', ScriptedLLM([text('ok')]))

        with pytest.raises(ValueError, match='topic'):
            await agent.run('Summarise <topic>.')


class TestInteractiveInputs:
    async def test_what_the_person_types_is_taken_as_written(self):
        llm = ScriptedLLM([text('ok')])
        agent = Agent('a', 'sys', llm, interactive=True)

        await agent.run('How do I centre a <div> inside <body>?')

        assert contents(llm.requests[0])[-1] == 'How do I centre a <div> inside <body>?'

    async def test_message_inputs_are_taken_as_written(self):
        llm = ScriptedLLM([text('ok')])
        agent = Agent('a', 'sys', llm, interactive=True)

        await agent.run(
            [UserMessage(content=TextMessageContent(text='What does <br> do?'))]
        )

        assert contents(llm.requests[0])[-1] == 'What does <br> do?'

    async def test_the_system_prompt_is_still_a_template(self):
        llm = ScriptedLLM([text('ok')])
        agent = Agent('a', 'You help <user_name>.', llm, interactive=True)

        await agent.run('What is <topic>?', variables={'user_name': 'Priya'})

        assert contents(llm.requests[0]) == ['You help Priya.', 'What is <topic>?']

    async def test_a_missing_prompt_variable_is_still_an_error(self):
        agent = Agent('a', 'You help <user_name>.', ScriptedLLM([]), interactive=True)

        with pytest.raises(ValueError, match='user_name'):
            await agent.run('hello')


class TestInteractiveTurns:
    async def test_a_question_goes_straight_back_to_the_person(self):
        events = []
        llm = ScriptedLLM([text('Which model should the agent use?')])
        agent = Agent('a', 'sys', llm, tools=[lookup_tool()], interactive=True)

        history = await agent.run('create an agent for me', on_event=events.append)

        assert history[-1].content == 'Which model should the agent use?'
        # One request: no classifier call, no request to keep going.
        assert len(llm.requests) == 1
        assert [(e.type, e.is_final) for e in events] == [
            (AgentEventType.MESSAGE, True)
        ]

    async def test_the_answer_after_a_tool_call_needs_no_classifier(self):
        llm = ScriptedLLM([call('lookup', query='x'), text('Here it is.')])
        agent = Agent('a', 'sys', llm, tools=[lookup_tool()], interactive=True)

        history = await agent.run('find x')

        assert history[-1].content == 'Here it is.'
        assert len(llm.requests) == 2

    async def test_the_next_turn_carries_on_from_the_question(self):
        llm = ScriptedLLM(
            [
                text('Which order?'),
                call('lookup', query='A-1'),
                text('It shipped.'),
            ]
        )
        agent = Agent('a', 'sys', llm, tools=[lookup_tool()], interactive=True)

        await agent.run('where is my order?')
        history = await agent.run('A-1')

        assert history[-1].content == 'It shipped.'
        assert contents(llm.requests[1])[1:] == [
            'where is my order?',
            'Which order?',
            'A-1',
        ]

    async def test_a_question_ends_the_turn_even_with_an_unfinished_plan(self):
        llm = ScriptedLLM(
            [
                plan(('pick a model', 'in_progress'), ('create the agent', 'pending')),
                text('Which model do you want?'),
            ]
        )
        agent = Agent(
            'a',
            'sys',
            llm,
            reasoning_pattern=ReasoningPattern.PLAN_EXECUTE,
            interactive=True,
        )

        history = await agent.run('create an agent')

        assert history[-1].content == 'Which model do you want?'
        assert len(llm.requests) == 2
        assert agent.plan.unfinished()

    async def test_without_interactive_a_question_is_still_checked(self):
        llm = ScriptedLLM([text('Which model should the agent use?'), text('FINAL')])
        agent = Agent('a', 'sys', llm, tools=[lookup_tool()])

        await agent.run('create an agent for me')

        # The second request is the final-answer classifier.
        assert len(llm.requests) == 2


class TestInteractiveConfiguration:
    def test_default_is_off(self):
        assert Agent('a', 'sys', ScriptedLLM([])).interactive is False

    def test_builder(self):
        agent = (
            AgentBuilder()
            .with_name('a')
            .with_prompt('sys')
            .with_llm(ScriptedLLM([]))
            .with_interactive()
            .build()
        )
        assert agent.interactive is True

    def test_yaml_setting(self):
        agent = AgentBuilder.from_yaml(
            yaml_str="""
agent:
  name: assistant
  job: Help the user.
  settings:
    interactive: true
""",
            base_llm=ScriptedLLM([]),
        ).build()

        assert agent.interactive is True
