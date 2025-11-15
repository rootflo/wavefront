import asyncio
from flo_ai import UserMessage
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.models import TextMessageContent
from flo_ai.tool.base_tool import Tool
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.llm.anthropic_llm import Anthropic


async def example_simple_agent():
    # Create a simple conversational agent with OpenAI
    agent = (
        AgentBuilder()
        .with_name('Math Tutor')
        .with_prompt('You are a helpful math tutor.')
        .with_llm(OpenAI(model='gpt-4o-mini'))
        .build()
    )

    response = await agent.run(
        [
            UserMessage(
                TextMessageContent(text='What is the formula for the area of a circle?')
            )
        ]
    )
    print(f'Simple Agent Response: {response}')


async def example_tool_agent():
    # Define a calculator tool
    async def calculate(operation: str, x: float, y: float) -> float:
        if operation == 'add':
            return x + y
        elif operation == 'multiply':
            return x * y
        raise ValueError(f'Unknown operation: {operation}')

    calculator_tool = Tool(
        name='calculate',
        description='Perform basic calculations',
        function=calculate,
        parameters={
            'operation': {
                'type': 'string',
                'description': 'The operation to perform (add or multiply)',
            },
            'x': {'type': 'number', 'description': 'First number'},
            'y': {'type': 'number', 'description': 'Second number'},
        },
    )

    # Create a tool-using agent with Claude
    agent_openai = (
        AgentBuilder()
        .with_name('Calculator Assistant')
        .with_prompt('You are a math assistant that can perform calculations.')
        .with_llm(OpenAI(model='gpt-4o', temperature=0.7))
        .with_tools([calculator_tool])
        .with_reasoning(ReasoningPattern.REACT)
        .with_retries(2)
        .build()
    )

    agent_claude = (
        AgentBuilder()
        .with_name('Calculator Assistant')
        .with_prompt('You are a math assistant that can perform calculations.')
        .with_llm(Anthropic(model='claude-sonnet-4-5', temperature=0.7))
        .with_tools([calculator_tool])
        .with_reasoning(ReasoningPattern.REACT)
        .with_retries(2)
        .build()
    )

    response = await agent_openai.run(
        [UserMessage(TextMessageContent(text='Calculate 5 plus 3'))]
    )
    print(f'OpenAI Tool Agent Response: {response}')

    response = await agent_claude.run(
        [UserMessage(TextMessageContent(text='Calculate 5 plus 3'))]
    )
    print(f'Claude Tool Agent Response: {response}')


async def example_structured_output():
    # Define output schema for structured responses
    math_schema = {
        'type': 'object',
        'properties': {
            'solution': {'type': 'string', 'description': 'The step-by-step solution'},
            'answer': {'type': 'string', 'description': 'The final answer'},
        },
        'required': ['solution', 'answer'],
    }

    # Create an agent with structured output
    agent = (
        AgentBuilder()
        .with_name('Structured Math Solver')
        .with_prompt(
            'You are a math problem solver that provides structured solutions.'
        )
        .with_llm(OpenAI(model='gpt-4o'))
        .with_output_schema(math_schema)
        .build()
    )

    response = await agent.run(
        [UserMessage(TextMessageContent(text='Solve: 2x + 5 = 15'))]
    )
    print(f'Structured Output Response: {response}')


async def main():
    print('\n=== Simple Conversational Agent ===')
    await example_simple_agent()

    print('\n=== Tool-using Agent ===')
    await example_tool_agent()

    print('\n=== Structured Output Agent ===')
    await example_structured_output()


if __name__ == '__main__':
    asyncio.run(main())
