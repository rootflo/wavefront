import asyncio
import os
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.tool.base_tool import Tool
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_vllm import OpenAIVLLM
from dotenv import load_dotenv

load_dotenv()

vllm_base_url = os.getenv('VLLM_BASE_URL')


async def example_simple_vllm_agent():
    # Create a simple conversational agent with vLLM
    agent = (
        AgentBuilder()
        .with_name('Math Tutor')
        .with_prompt('You are a helpful math tutor.')
        .with_llm(
            OpenAIVLLM(
                model='microsoft/phi-4',
                base_url=vllm_base_url,
                temperature=0.7,
                api_key='',
            )
        )
        .build()
    )

    response = await agent.run('What is the formula for the area of a circle?')
    print(f'vLLM Simple Agent Response: {response}')


async def example_vllm_tool_agent():
    # Define a calculator tool
    async def calculate(operation: str, x: float, y: float) -> float:
        if operation == 'add':
            return x + y
        elif operation == 'multiply':
            return x * y
        elif operation == 'subtract':
            return x - y
        elif operation == 'divide':
            return x / y if y != 0 else float('inf')
        raise ValueError(f'Unknown operation: {operation}')

    calculator_tool = Tool(
        name='calculate',
        description='Perform basic calculations',
        function=calculate,
        parameters={
            'operation': {
                'type': 'string',
                'description': 'The operation to perform (add, subtract, multiply, or divide)',
            },
            'x': {'type': 'number', 'description': 'First number'},
            'y': {'type': 'number', 'description': 'Second number'},
        },
    )

    # Create a tool-using agent with vLLM
    agent = (
        AgentBuilder()
        .with_name('vLLM Calculator Assistant')
        .with_prompt(
            'You are a math assistant that can perform calculations using tools.'
        )
        .with_llm(
            OpenAIVLLM(
                model='microsoft/phi-4',
                base_url=vllm_base_url,
                temperature=0.7,
                api_key='',
            )
        )
        .with_tools([calculator_tool])
        .with_reasoning(ReasoningPattern.REACT)
        .with_retries(2)
        .build()
    )

    response = await agent.run(
        'Calculate 15 divided by 3, then multiply the result by 7'
    )
    print(f'vLLM Tool Agent Response: {response}')


async def example_vllm_structured_output():
    # Define output schema for structured responses with name field
    math_schema = {
        'name': 'math_solution',
        'schema': {
            'type': 'object',
            'properties': {
                'problem': {'type': 'string', 'description': 'The original problem'},
                'steps': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Step-by-step solution process',
                },
                'final_answer': {
                    'type': 'string',
                    'description': 'The final numerical answer',
                },
                'explanation': {
                    'type': 'string',
                    'description': 'Brief explanation of the approach used',
                },
            },
            'required': ['problem', 'steps', 'final_answer', 'explanation'],
        },
    }

    # Create an agent with structured output using vLLM
    agent = (
        AgentBuilder()
        .with_name('vLLM Structured Math Solver')
        .with_prompt(
            'You are a math problem solver that provides detailed structured solutions. '
            'Always break down problems into clear steps and explain your reasoning.'
        )
        .with_llm(
            OpenAIVLLM(
                model='microsoft/phi-4',
                base_url=vllm_base_url,
                temperature=0.3,
                api_key='',
            )
        )
        .with_output_schema(math_schema)
        .build()
    )

    response = await agent.run('Solve the equation: x + y = 4, x - y = 1')
    print(f'vLLM Structured Output Response: {response}')


async def example_vllm_tool_agent_structured_output():
    # Define a calculator tool
    async def calculate(operation: str, x: float, y: float) -> float:
        if operation == 'add':
            return x + y
        elif operation == 'multiply':
            return x * y
        elif operation == 'subtract':
            return x - y
        elif operation == 'divide':
            return x / y if y != 0 else float('inf')
        raise ValueError(f'Unknown operation: {operation}')

    calculator_tool = Tool(
        name='calculate',
        description='Perform basic calculations',
        function=calculate,
        parameters={
            'operation': {
                'type': 'string',
                'description': 'The operation to perform (add, subtract, multiply, or divide)',
            },
            'x': {'type': 'number', 'description': 'First number'},
            'y': {'type': 'number', 'description': 'Second number'},
        },
    )

    # Define structured output schema for calculation results
    calculation_report_schema = {
        'name': 'calculation_report',
        'schema': {
            'type': 'object',
            'properties': {
                'task': {
                    'type': 'string',
                    'description': 'Description of the calculation task',
                },
                'calculations': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'operation': {
                                'type': 'string',
                                'description': 'The operation performed',
                            },
                            'numbers': {
                                'type': 'string',
                                'description': 'The numbers used',
                            },
                            'result': {
                                'type': 'number',
                                'description': 'The result of the operation',
                            },
                        },
                        'required': ['operation', 'numbers', 'result'],
                    },
                    'description': 'List of calculations performed',
                },
                'final_answer': {
                    'type': 'number',
                    'description': 'The final numerical result',
                },
                'summary': {
                    'type': 'string',
                    'description': 'Summary of the calculation process',
                },
            },
            'required': ['task', 'calculations', 'final_answer', 'summary'],
        },
    }

    # Create a tool-using agent with structured output
    agent = (
        AgentBuilder()
        .with_name('vLLM Calculator with Reports')
        .with_prompt(
            'You are a calculator assistant that performs calculations using tools and provides structured reports.'
        )
        .with_llm(
            OpenAIVLLM(
                model='microsoft/phi-4',
                base_url=vllm_base_url,
                temperature=0.3,
                api_key='',
            )
        )
        .with_tools([calculator_tool])
        .with_reasoning(ReasoningPattern.REACT)
        .with_output_schema(calculation_report_schema)
        .build()
    )

    response = await agent.run(
        'Calculate 25 multiplied by 4, then add 15 to the result'
    )
    print(f'vLLM Tool + Structured Output Response: {response}')


async def main():
    print('=== vLLM Agent Examples ===')
    print(f'Note: Make sure vLLM server is running at {vllm_base_url}')

    print('\n=== Simple vLLM Conversational Agent ===')
    await example_simple_vllm_agent()

    print('\n=== vLLM Tool-using Agent ===')
    await example_vllm_tool_agent()

    print('\n=== vLLM Structured Output Agent ===')
    await example_vllm_structured_output()

    print('\n=== vLLM Tool Agent with Structured Output ===')
    await example_vllm_tool_agent_structured_output()


if __name__ == '__main__':
    asyncio.run(main())
