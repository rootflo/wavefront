import asyncio
from typing import Any
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI
from flo_ai.models.agent import Agent
from flo_ai.models.chat_message import ChatMessage


async def main() -> None:
    # Create a simple conversational agent
    agent: Agent = (
        AgentBuilder()
        .with_name('Math Tutor')
        .with_prompt('You are a helpful math tutor.')
        .with_llm(OpenAI(model='gpt-4o-mini'))
        .build()
    )

    response: Any = await agent.run(
        [
            ChatMessage(
                role='user', content='What is the formula for the area of a circle?'
            ),
            ChatMessage(
                role='assistant',
                content='The formula for the area of a circle is πr^2.',
            ),
            ChatMessage(
                role='user', content='What is the formula for the area of a rectangle?'
            ),
            ChatMessage(
                role='assistant',
                content='The formula for the area of a rectangle is length * width.',
            ),
            ChatMessage(
                role='user', content='What is the formula for the area of a triangle?'
            ),
        ]
    )
    print(f'Response: {response}')


asyncio.run(main())
