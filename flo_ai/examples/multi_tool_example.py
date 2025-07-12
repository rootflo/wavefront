import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.tool.base_tool import Tool
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_llm import OpenAI

from flo_ai.llm.anthropic_llm import Anthropic
from flo_ai.llm.base_llm import BaseLLM


async def create_tools():
    """Create a set of tools for the agents to use"""

    # Calculator tool
    async def calculate(operation: str, x: float, y: float) -> float:
        operations = {
            'add': lambda: x + y,
            'subtract': lambda: x - y,
            'multiply': lambda: x * y,
            'divide': lambda: x / y if y != 0 else 'Cannot divide by zero',
        }
        if operation not in operations:
            raise ValueError(f'Unknown operation: {operation}')
        return operations[operation]()

    calculator_tool = Tool(
        name='calculate',
        description='Perform basic calculations (add, subtract, multiply, divide)',
        function=calculate,
        parameters={
            'operation': {
                'type': 'string',
                'description': 'The operation to perform (add, subtract, multiply, divide)',
            },
            'x': {'type': 'number', 'description': 'First number'},
            'y': {'type': 'number', 'description': 'Second number'},
        },
    )

    # Unit conversion tool
    async def convert_units(value: float, from_unit: str, to_unit: str) -> str:
        conversions = {
            ('km', 'miles'): lambda x: x * 0.621371,
            ('miles', 'km'): lambda x: x * 1.60934,
            ('kg', 'lbs'): lambda x: x * 2.20462,
            ('lbs', 'kg'): lambda x: x * 0.453592,
            ('celsius', 'fahrenheit'): lambda x: (x * 9 / 5) + 32,
            ('fahrenheit', 'celsius'): lambda x: (x - 32) * 5 / 9,
        }

        key = (from_unit.lower(), to_unit.lower())
        if key not in conversions:
            raise ValueError(f'Unsupported conversion: {from_unit} to {to_unit}')

        result = conversions[key](value)
        return f'{value} {from_unit} = {result:.2f} {to_unit}'

    converter_tool = Tool(
        name='convert_units',
        description='Convert between different units (km/miles, kg/lbs, celsius/fahrenheit)',
        function=convert_units,
        parameters={
            'value': {'type': 'number', 'description': 'The value to convert'},
            'from_unit': {'type': 'string', 'description': 'The unit to convert from'},
            'to_unit': {'type': 'string', 'description': 'The unit to convert to'},
        },
    )

    # Weather tool (mock)
    async def get_weather(city: str, country: str = None) -> str:
        # This is a mock weather tool - in real use, you'd call a weather API
        weather_data = {
            'london': {'temp': 18, 'condition': 'cloudy'},
            'paris': {'temp': 22, 'condition': 'sunny'},
            'new york': {'temp': 25, 'condition': 'partly cloudy'},
            'tokyo': {'temp': 28, 'condition': 'rainy'},
        }

        city_key = city.lower()
        if city_key not in weather_data:
            return f'Weather data for {city} is not available'

        data = weather_data[city_key]
        location = f'{city}, {country}' if country else city
        return f"Current weather in {location}: {data['temp']}°C, {data['condition']}"

    weather_tool = Tool(
        name='get_weather',
        description='Get current weather information for a city',
        function=get_weather,
        parameters={
            'city': {'type': 'string', 'description': 'The city to get weather for'},
            'country': {
                'type': 'string',
                'description': 'The country (optional)',
                'required': False,
            },
        },
    )

    return [calculator_tool, converter_tool, weather_tool]


async def test_multi_tool_agent(llm: BaseLLM, agent_name: str):
    tools = await create_tools()

    agent = (
        AgentBuilder()
        .with_name(agent_name)
        .with_prompt("""You are a helpful assistant that can perform calculations, 
                           unit conversions, and check weather information. 
                           Use the available tools to provide accurate responses.""")
        .with_llm(llm)
        .with_tools(tools)
        .with_reasoning(ReasoningPattern.REACT)
        .with_retries(2)
        .build()
    )

    # Test cases that require multiple tool usage
    test_queries = [
        "If it's 25°C in Paris, what's that in Fahrenheit? Also, how's the weather there?",
        "I'm planning a 10 km run in London. How many miles is that, and what's the weather like for running?",
        'If I have 2.5 kg of flour and need to triple it for a large batch, how many pounds would that be?',
    ]

    print(f'\n=== Testing {agent_name} ===')
    for query in test_queries:
        print(f'\nQuery: {query}')
        response = await agent.run(query)
        print(f'Response: {response}')
        print('-' * 80)


async def main():
    # Test with OpenAI
    openai_llm = OpenAI(model='gpt-4-turbo-preview', temperature=0.7)
    await test_multi_tool_agent(openai_llm, 'OpenAI Multi-Tool Agent')

    # # Test with Claude
    claude_llm = Anthropic(model='claude-3-5-sonnet-20240620', temperature=0.7)
    await test_multi_tool_agent(claude_llm, 'Claude Multi-Tool Agent')


if __name__ == '__main__':
    asyncio.run(main())
