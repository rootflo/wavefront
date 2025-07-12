import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.tool import flo_tool, create_tool_from_function
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.llm.anthropic_llm import Anthropic
from flo_ai.llm.base_llm import BaseLLM


# Example 1: Using the @flo_tool decorator with parameter descriptions
@flo_tool(
    description='Perform basic calculations (add, subtract, multiply, divide)',
    parameter_descriptions={
        'operation': 'The operation to perform (add, subtract, multiply, divide)',
        'x': 'First number',
        'y': 'Second number',
    },
)
async def calculate(operation: str, x: float, y: float) -> float:
    """Calculate mathematical operations between two numbers."""
    operations = {
        'add': lambda: x + y,
        'subtract': lambda: x - y,
        'multiply': lambda: x * y,
        'divide': lambda: x / y if y != 0 else 'Cannot divide by zero',
    }
    if operation not in operations:
        raise ValueError(f'Unknown operation: {operation}')
    return operations[operation]()


# Example 2: Using the @flo_tool decorator with docstring-based descriptions
@flo_tool()
async def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert between different units (km/miles, kg/lbs, celsius/fahrenheit).

    Args:
        value: The value to convert
        from_unit: The unit to convert from
        to_unit: The unit to convert to
    """
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


# Example 3: Using the @flo_tool decorator with custom name
@flo_tool(
    name='weather_checker', description='Get current weather information for a city'
)
async def get_weather(city: str, country: str = None) -> str:
    """Get weather information for a specific city."""
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


# Example 4: Regular function that we'll convert to a tool later
async def format_text(text: str, style: str = 'normal') -> str:
    """Format text in different styles."""
    styles = {
        'uppercase': text.upper(),
        'lowercase': text.lower(),
        'title': text.title(),
        'normal': text,
    }
    return styles.get(style, text)


async def test_flo_tool_decorator():
    """Test the @flo_tool decorator functionality."""
    print('=== Testing @flo_tool Decorator ===\n')

    # Test 1: Function can be called normally
    print('1. Testing function calls:')
    result1 = await calculate('add', 5, 3)
    print(f"   calculate('add', 5, 3) = {result1}")

    result2 = await convert_units(10, 'km', 'miles')
    print(f"   convert_units(10, 'km', 'miles') = {result2}")

    result3 = await get_weather('Paris', 'France')
    print(f"   get_weather('Paris', 'France') = {result3}")

    # Test 2: Tool objects are accessible via .tool attribute
    print('\n2. Testing tool objects:')
    print(f'   calculate.tool.name = {calculate.tool.name}')
    print(f'   calculate.tool.description = {calculate.tool.description}')
    print(f'   calculate.tool.parameters = {calculate.tool.parameters}')

    print(f'   convert_units.tool.name = {convert_units.tool.name}')
    print(f'   get_weather.tool.name = {get_weather.tool.name}')

    # Test 3: Using create_tool_from_function for existing functions
    print('\n3. Testing create_tool_from_function:')
    format_tool = create_tool_from_function(
        format_text,
        name='text_formatter',
        description='Format text in different styles',
        parameter_descriptions={
            'text': 'The text to format',
            'style': 'The formatting style (uppercase, lowercase, title, normal)',
        },
    )
    print(f'   format_tool.name = {format_tool.name}')
    print(f'   format_tool.parameters = {format_tool.parameters}')


async def test_multi_tool_agent_with_decorator(llm: BaseLLM, agent_name: str):
    """Test the decorated tools with an agent."""
    # Collect all tools from decorated functions
    tools = [
        calculate.tool,
        convert_units.tool,
        get_weather.tool,
        create_tool_from_function(
            format_text,
            name='text_formatter',
            description='Format text in different styles',
        ),
    ]

    agent = (
        AgentBuilder()
        .with_name(agent_name)
        .with_prompt("""You are a helpful assistant that can perform calculations, 
                           unit conversions, check weather information, and format text. 
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
        "Format the text 'hello world' in uppercase and then convert 5 miles to kilometers",
    ]

    print(f'\n=== Testing {agent_name} with @flo_tool decorated functions ===')
    for query in test_queries:
        print(f'\nQuery: {query}')
        response = await agent.run(query)
        print(f'Response: {response}')
        print('-' * 80)


async def main():
    # Test the decorator functionality
    await test_flo_tool_decorator()

    # Test with OpenAI
    openai_llm = OpenAI(model='gpt-40-mini', temperature=0.7)
    await test_multi_tool_agent_with_decorator(openai_llm, 'OpenAI @flo_tool Agent')

    # Test with Claude
    claude_llm = Anthropic(model='claude-3-5-sonnet-20240620', temperature=0.7)
    await test_multi_tool_agent_with_decorator(claude_llm, 'Claude @flo_tool Agent')


if __name__ == '__main__':
    asyncio.run(main())
