import asyncio
from typing import Any
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.tool.base_tool import Tool
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.models.agent import Agent
from flo_ai.llm import Anthropic


async def calculate(operation: str, x: float, y: float) -> float:
    if operation == 'add':
        return x + y
    elif operation == 'multiply':
        return x * y
    raise ValueError(f'Unknown operation: {operation}')


# Define a calculator tool
calculator_tool: Tool = Tool(
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
agent: Agent = (
    AgentBuilder()
    .with_name('Calculator Assistant')
    .with_prompt('You are a math assistant that can perform calculations.')
    .with_llm(Anthropic(model='claude-sonnet-4-5-20250929'))
    .with_tools([calculator_tool])
    .with_reasoning(ReasoningPattern.REACT)
    .with_retries(2)
    .build()
)


async def main() -> None:
    response: Any = await agent.run('Calculate 5 plus 3')
    print(f'Response: {response}')


asyncio.run(main())
