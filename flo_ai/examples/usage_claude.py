import asyncio
import os
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.models.agent import Agent as ToolAgent
from flo_ai.llm.anthropic_llm import Anthropic
from flo_ai.tool.base_tool import Tool
from flo_ai.models.agent_error import AgentError


async def test_claude_conversational():
    # Initialize Claude LLM
    claude_llm = Anthropic(
        model='claude-3-5-sonnet-20240620',
        temperature=0.7,
        api_key=os.getenv('ANTHROPIC_API_KEY'),
    )

    # Create conversational agent with Claude
    agent = ToolAgent(
        name='ClaudeAssistant',
        system_prompt='You are a helpful AI assistant powered by Claude.',
        llm=claude_llm,
    )

    try:
        response = await agent.run(
            'What are the main differences between Python and JavaScript?'
        )
        print('\nConversational Agent Response:')
        print(response)
    except AgentError as e:
        print(f'Error: {str(e)}')


async def test_claude_tool_agent():
    # Example weather tool
    async def get_weather(city: str, country: str = None) -> str:
        location = f'{city}, {country}' if country else city
        # This would normally call a weather API
        return f"Currently in {location}, it's sunny and warm with a temperature of 25°C (77°F)."

    weather_tool = Tool(
        name='get_weather',
        description='Get the current weather for a city',
        function=get_weather,
        parameters={
            'city': {'type': 'string', 'description': 'The city to get weather for'},
            'country': {
                'type': 'string',
                'description': 'The country of the city (optional)',
                'required': False,
            },
        },
    )

    # Initialize Claude LLM
    claude_llm = Anthropic(
        model='claude-3-5-sonnet-20240620',
        temperature=0.7,
        api_key=os.getenv('ANTHROPIC_API_KEY'),
    )

    # Create tool agent with Claude
    agent = ToolAgent(
        name='ClaudeWeatherAssistant',
        system_prompt="""You are a helpful weather assistant. When asked about weather, always use the weather tool to get information.
        After getting the weather information, provide a natural response incorporating the data.
        Do not just think about using the tool - actually use it and share the results.""",
        llm=claude_llm,
        tools=[weather_tool],
        max_retries=1,
    )

    try:
        # Test with different queries
        queries = [
            "What's the weather like in Tokyo?",
            'Tell me the weather in Paris, France',
            "How's the weather in New York City, USA?",
        ]

        for query in queries:
            print(f'\nQuery: {query}')
            response = await agent.run(query)
            print(f'Response: {response}')

    except AgentError as e:
        print(f'Error: {str(e)}')
        if e.original_error:
            print(f'Original error: {str(e.original_error)}')


async def test_error_handling():
    # Example of a tool that might fail
    async def flaky_weather(city: str) -> str:
        if city.lower() == 'error':
            raise ValueError('API temporarily unavailable')
        return f'The weather in {city} is sunny'

    weather_tool = Tool(
        name='get_weather',
        description='Get the weather for a city',
        function=flaky_weather,
        parameters={
            'city': {'type': 'string', 'description': 'The city to get weather for'}
        },
    )

    claude_llm = Anthropic(
        model='claude-3-opus-20240229',
        temperature=0.7,
        api_key=os.getenv('ANTHROPIC_API_KEY'),
    )

    agent = ToolAgent(
        name='ClaudeWeatherAssistant',
        system_prompt='You are a helpful weather assistant.',
        llm=claude_llm,
        tools=[weather_tool],
        max_retries=3,
    )

    try:
        # This will trigger error handling and retries
        response = await agent.run("What's the weather like in error?")
        print('\nResponse:', response)
    except AgentError as e:
        print('\nAgent error:', str(e))
        if e.original_error:
            print('Original error:', str(e.original_error))


async def test_direct_reasoning():
    # Define a simple calculator tool
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

    claude_llm = Anthropic(
        model='claude-3-5-sonnet-20240620',
        temperature=0.7,
        api_key=os.getenv('ANTHROPIC_API_KEY'),
    )

    agent = ToolAgent(
        name='ClaudeCalculatorAssistant',
        system_prompt='You are a helpful calculator assistant. Use the calculator tool directly without explanation.',
        llm=claude_llm,
        tools=[calculator_tool],
        reasoning_pattern=ReasoningPattern.DIRECT,
    )

    response = await agent.run('Calculate 5 plus 3')
    print('\nDirect Reasoning Response:', response)


async def main():
    print('\n=== Testing Claude Conversational Agent ===')
    await test_claude_conversational()

    print('\n=== Testing Claude Tool Agent ===')
    await test_claude_tool_agent()

    print('\n=== Testing Error Handling ===')
    await test_error_handling()

    print('\n=== Testing Direct Reasoning ===')
    await test_direct_reasoning()


if __name__ == '__main__':
    asyncio.run(main())
