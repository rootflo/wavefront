import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm.ollama_llm import OllamaLLM
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.tool.base_tool import Tool


async def create_tools():
    """Create a set of tools for the Ollama agent to use"""

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
        }

        key = (from_unit.lower(), to_unit.lower())
        if key not in conversions:
            raise ValueError(f'Unsupported conversion: {from_unit} to {to_unit}')

        result = conversions[key](value)
        return f'{value} {from_unit} = {result:.2f} {to_unit}'

    converter_tool = Tool(
        name='convert_units',
        description='Convert between different units (km/miles, kg/lbs)',
        function=convert_units,
        parameters={
            'value': {'type': 'number', 'description': 'The value to convert'},
            'from_unit': {'type': 'string', 'description': 'The unit to convert from'},
            'to_unit': {'type': 'string', 'description': 'The unit to convert to'},
        },
    )

    return [calculator_tool, converter_tool]


async def example_ollama_agent():
    # Create an Ollama LLM instance using the phi4 model
    ollama_llm = OllamaLLM(
        model='phi4', temperature=0.7, base_url='http://localhost:11434'
    )

    # Create a simple conversational agent with Ollama
    agent = (
        AgentBuilder()
        .with_name('Ollama Assistant')
        .with_prompt('You are a helpful AI assistant powered by Ollama.')
        .with_llm(ollama_llm)
        .with_retries(2)
        .build()
    )

    # Test the agent with a simple question
    response = await agent.run('What is the capital of France?')
    print(f'Ollama Agent Response: {response}')


async def example_ollama_structured_output():
    # Define output schema for structured responses
    location_schema = {
        'type': 'object',
        'properties': {
            'city': {'type': 'string', 'description': 'The name of the city'},
            'country': {'type': 'string', 'description': 'The name of the country'},
            'population': {
                'type': 'number',
                'description': 'The population of the city',
            },
        },
        'required': ['city', 'country', 'population'],
    }

    # Create an Ollama LLM instance using the llama3.2:1b model
    ollama_llm = OllamaLLM(
        model='llama3.2:1b', temperature=0.7, base_url='http://localhost:11434'
    )

    # Create an agent with structured output
    agent = (
        AgentBuilder()
        .with_name('Structured Location Assistant')
        .with_prompt(
            'You are a location information assistant that provides structured data about cities.'
        )
        .with_llm(ollama_llm)
        .with_output_schema(location_schema)
        .build()
    )

    response = await agent.run('Tell me about Tokyo')
    print(f'Structured Output Response: {response}')


async def example_ollama_tools():
    # Create an Ollama LLM instance using the phi4 model
    ollama_llm = OllamaLLM(
        model='phi4', temperature=0.7, base_url='http://localhost:11434'
    )

    # Create tools
    tools = await create_tools()

    # Create a tool-using agent with Ollama
    agent = (
        AgentBuilder()
        .with_name('Ollama Tool Assistant')
        .with_prompt("""You are a helpful assistant that can perform calculations and unit conversions.
                       Use the available tools to provide accurate responses.""")
        .with_llm(ollama_llm)
        .with_tools(tools)
        .with_reasoning(ReasoningPattern.REACT)
        .with_retries(2)
        .build()
    )

    # Test cases that require tool usage
    test_queries = [
        'What is 25 kilometers in miles?',
        'If I have 2.5 kg of flour and need to triple it, how many pounds would that be?',
        'Calculate 15 multiplied by 7 and then convert the result from kg to lbs',
    ]

    print('\n=== Testing Ollama Tool Agent ===')
    for query in test_queries:
        print(f'\nQuery: {query}')
        response = await agent.run(query)
        print(f'Response: {response}')
        print('-' * 80)


async def main():
    print('\n=== Simple Ollama Conversational Agent ===')
    await example_ollama_agent()

    print('\n=== Ollama Structured Output Agent ===')
    await example_ollama_structured_output()

    print('\n=== Ollama Tool Agent ===')
    await example_ollama_tools()


if __name__ == '__main__':
    asyncio.run(main())
