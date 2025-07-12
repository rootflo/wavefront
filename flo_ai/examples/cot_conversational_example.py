#!/usr/bin/env python3
"""
Example demonstrating Chain of Thought (CoT) reasoning pattern in conversational mode.
"""

import asyncio
from flo_ai.models.agent import Agent
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_llm import OpenAI
import os


async def main():
    """Main function demonstrating conversational CoT reasoning"""

    # Initialize LLM (you'll need to set OPENAI_API_KEY environment variable)
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('Please set OPENAI_API_KEY environment variable')
        return

    llm = OpenAI(model='gpt-3.5-turbo')

    # Create agent with CoT reasoning pattern (no tools)
    agent = Agent(
        name='CoT Reasoning Agent',
        system_prompt='You are a helpful assistant that thinks through problems step by step.',
        llm=llm,
        tools=None,  # No tools for conversational mode
        reasoning_pattern=ReasoningPattern.COT,
        role='Problem Solver',
    )

    # Test questions that require step-by-step reasoning
    questions = [
        'If a train leaves station A at 2 PM traveling 60 mph and another train leaves station B at 3 PM traveling 80 mph, and the stations are 300 miles apart, when will they meet?',
        'A store has a 20% discount on all items. If a customer buys 3 items that originally cost $50, $30, and $20, what is the final total after the discount?',
        'Explain why the sky appears blue during the day but red during sunset.',
    ]

    print('=== Conversational Chain of Thought (CoT) Reasoning Demo ===\n')

    for i, question in enumerate(questions, 1):
        print(f'Question {i}: {question}')
        print('-' * 50)

        try:
            response = await agent.run(question)
            print(f'Answer: {response}')
        except Exception as e:
            print(f'Error: {e}')

        print('\n' + '=' * 60 + '\n')


if __name__ == '__main__':
    asyncio.run(main())
