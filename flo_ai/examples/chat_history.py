import asyncio
from typing import Any
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import Gemini
from flo_ai.models.agent import Agent
from flo_ai.models import (
    AssistantMessage,
    UserMessage,
    TextMessageContent,
)
from flo_ai.tool import flo_tool


@flo_tool(
    description='Calculate the area of a rectangle',
    parameter_descriptions={
        'length': 'Length of the rectangle',
        'breadth': 'Breadth of the rectangle',
    },
)
async def calculate(length: float, breadth: float) -> float:
    """Calculate the area of a rectangle."""
    return length * breadth


async def main() -> None:
    # Create a simple conversational agent
    agent: Agent = (
        AgentBuilder()
        .with_name('Math Tutor')
        .with_prompt('You are a helpful math tutor.')
        .with_llm(Gemini(model='gemini-2.5-flash'))
        .add_tool(calculate.tool)
        .build()
    )

    response: Any = await agent.run(
        [
            UserMessage(
                TextMessageContent(
                    text='What is the formula for the area of a circle?'
                ),
            ),
            AssistantMessage(
                TextMessageContent(
                    text='The formula for the area of a circle is πr^2.'
                ),
            ),
            UserMessage(
                TextMessageContent(
                    text='What is the formula for the area of a rectangle?'
                )
            ),
            AssistantMessage(
                TextMessageContent(
                    text='The formula for the area of a rectangle is length * width.',
                ),
            ),
            UserMessage(
                TextMessageContent(
                    text='What is the area of a rectable of length <length> and breadth <breadth>',
                ),
            ),
        ],
        variables={'length': 10, 'breadth': 70},
    )
    print(f'Response: {response}')


asyncio.run(main())
