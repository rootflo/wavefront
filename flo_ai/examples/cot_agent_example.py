#!/usr/bin/env python3
"""
Example demonstrating Chain of Thought (CoT) reasoning pattern in the Agent class.
"""

import asyncio
from flo_ai.models.agent import Agent
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.tool.base_tool import Tool
import os


class CalculatorTool(Tool):
    """Simple calculator tool for demonstration"""

    def __init__(self):
        # Define the calculator function
        async def calculator_function(operation: str, a: float, b: float) -> str:
            if operation == 'add':
                result = a + b
            elif operation == 'subtract':
                result = a - b
            elif operation == 'multiply':
                result = a * b
            elif operation == 'divide':
                if b == 0:
                    raise ValueError('Cannot divide by zero')
                result = a / b
            else:
                raise ValueError(f'Unknown operation: {operation}')

            return f'{a} {operation} {b} = {result}'

        super().__init__(
            name='calculator',
            description='Performs basic arithmetic operations (add, subtract, multiply, divide)',
            function=calculator_function,
            parameters={
                'operation': {
                    'type': 'string',
                    'enum': ['add', 'subtract', 'multiply', 'divide'],
                    'description': 'The arithmetic operation to perform',
                },
                'a': {'type': 'number', 'description': 'First number'},
                'b': {'type': 'number', 'description': 'Second number'},
            },
        )


async def main():
    """Main function demonstrating CoT reasoning"""

    # Initialize LLM (you'll need to set OPENAI_API_KEY environment variable)
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('Please set OPENAI_API_KEY environment variable')
        return

    llm = OpenAI(model='gpt-4o-mini', api_key=api_key)

    # Create tools
    tools = [CalculatorTool()]

    # Create agent with CoT reasoning pattern
    agent = Agent(
        name='CoT Calculator Agent',
        system_prompt='You are a helpful math assistant that solves problems step by step.',
        llm=llm,
        tools=tools,
        reasoning_pattern=ReasoningPattern.COT,
        role='Math Assistant',
    )

    # Test questions
    questions = [
        'What is 15 + 27?',
        'If I have 100 apples and I give away 23, then buy 15 more, how many do I have?',
        'Calculate 8 * 7 and then add 12 to the result.',
    ]

    print('=== Chain of Thought (CoT) Reasoning Demo ===\n')

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
