#!/usr/bin/env python3
"""
Example demonstrating VertexAI LLM usage with different agent configurations.
This example shows how to use Google's VertexAI through the Gemini API
for conversational agents, tool usage, and structured output.
"""

import asyncio
import os
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm.vertexai_llm import VertexAI
from flo_ai.models.agent import Agent as ToolAgent
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.tool.base_tool import Tool
from flo_ai.models.agent_error import AgentError


async def create_tools():
    """Create a set of tools for the VertexAI agent to use"""

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

    # Weather tool (mock implementation)
    async def get_weather(city: str, country: str = None) -> str:
        location = f'{city}, {country}' if country else city
        # This would normally call a weather API
        return f"Currently in {location}, it's sunny and warm with a temperature of 24°C (75°F)."

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

    return [calculator_tool, weather_tool]


async def example_vertexai_conversational():
    """Test VertexAI with simple conversational agent"""

    # Initialize VertexAI LLM
    # You'll need to set up proper Google Cloud credentials
    vertexai_llm = VertexAI(
        model='gemini-2.5-flash',
        temperature=0.7,
        project=os.getenv('GOOGLE_CLOUD_PROJECT'),  # Your GCP project ID
        location=os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1'),  # GCP region
    )

    # Create a simple conversational agent with VertexAI
    agent = (
        AgentBuilder()
        .with_name('VertexAI Assistant')
        .with_prompt('You are a helpful AI assistant powered by Google VertexAI.')
        .with_llm(vertexai_llm)
        .with_retries(2)
        .build()
    )

    # Test the agent with various questions
    test_queries = [
        'What is the capital of France?',
        'Explain quantum computing in simple terms.',
        'What are the benefits of using cloud computing?',
    ]

    print('\n=== VertexAI Conversational Agent ===')
    for query in test_queries:
        print(f'\nQuery: {query}')
        try:
            response = await agent.run(query)
            print(f'Response: {response}')
        except Exception as e:
            print(f'Error: {e}')
        print('-' * 80)


async def example_vertexai_tool_agent():
    """Test VertexAI with tool-using agent"""

    # Initialize VertexAI LLM
    vertexai_llm = VertexAI(
        model='gemini-2.5-flash',
        temperature=0.7,
        project=os.getenv('GOOGLE_CLOUD_PROJECT'),
        location=os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1'),
    )

    # Create tools
    tools = await create_tools()

    # Create a tool-using agent with VertexAI
    agent = (
        AgentBuilder()
        .with_name('VertexAI Tool Assistant')
        .with_prompt("""You are a helpful assistant that can perform calculations and get weather information.
                       Use the available tools to provide accurate responses. When asked about calculations,
                       use the calculate tool. When asked about weather, use the get_weather tool.""")
        .with_llm(vertexai_llm)
        .with_tools(tools)
        .with_reasoning(ReasoningPattern.REACT)
        .with_retries(2)
        .build()
    )

    # Test cases that require tool usage
    test_queries = [
        'What is 25 multiplied by 4?',
        "What's the weather like in Tokyo?",
        'Calculate 100 divided by 8, then tell me the weather in Paris, France',
        'If I have 15 apples and give away 7, how many do I have left?',
    ]

    print('\n=== VertexAI Tool Agent ===')
    for query in test_queries:
        print(f'\nQuery: {query}')
        try:
            response = await agent.run(query)
            print(f'Response: {response}')
        except Exception as e:
            print(f'Error: {e}')
        print('-' * 80)


async def example_vertexai_structured_output():
    """Test VertexAI with structured output"""

    # Define output schema for structured responses
    analysis_schema = {
        'type': 'object',
        'properties': {
            'sentiment': {
                'type': 'string',
                'description': 'The overall sentiment (positive, negative, neutral)',
                'enum': ['positive', 'negative', 'neutral'],
            },
            'confidence': {
                'type': 'number',
                'description': 'Confidence score between 0 and 1',
                'minimum': 0,
                'maximum': 1,
            },
            'key_topics': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'Main topics discussed in the text',
            },
            'summary': {'type': 'string', 'description': 'Brief summary of the text'},
        },
        'required': ['sentiment', 'confidence', 'key_topics', 'summary'],
    }

    # Initialize VertexAI LLM
    vertexai_llm = VertexAI(
        model='gemini-2.5-flash',
        temperature=0.3,  # Lower temperature for more consistent structured output
        project=os.getenv('GOOGLE_CLOUD_PROJECT'),
        location=os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1'),
    )

    # Create an agent with structured output
    agent = (
        AgentBuilder()
        .with_name('VertexAI Text Analyzer')
        .with_prompt("""You are a text analysis assistant that analyzes sentiment and extracts key information.
                       Provide structured analysis of the given text.""")
        .with_llm(vertexai_llm)
        .with_output_schema(analysis_schema)
        .build()
    )

    # Test texts for analysis
    test_texts = [
        "I absolutely love this new product! It's innovative, well-designed, and has exceeded all my expectations. The customer service was also fantastic.",
        "The service was okay, nothing special. It worked as expected but didn't really impress me. Could be better.",
        'This is terrible! The product broke after just one day and customer support was completely unhelpful. Very disappointed.',
    ]

    print('\n=== VertexAI Structured Output ===')
    for i, text in enumerate(test_texts, 1):
        print(f'\nTest {i}: {text[:50]}...')
        try:
            response = await agent.run(f'Analyze this text: "{text}"')
            print(f'Analysis: {response}')
        except Exception as e:
            print(f'Error: {e}')
        print('-' * 80)


async def example_vertexai_error_handling():
    """Test VertexAI error handling and retries"""

    # Create a tool that might fail to test error handling
    async def flaky_service(query: str) -> str:
        if 'error' in query.lower():
            raise ValueError('Service temporarily unavailable')
        return f'Successfully processed: {query}'

    flaky_tool = Tool(
        name='flaky_service',
        description='A service that might fail occasionally',
        function=flaky_service,
        parameters={'query': {'type': 'string', 'description': 'The query to process'}},
    )

    # Initialize VertexAI LLM
    vertexai_llm = VertexAI(
        model='gemini-2.5-flash',
        temperature=0.7,
        project=os.getenv('GOOGLE_CLOUD_PROJECT'),
        location=os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1'),
    )

    # Create agent with error handling
    agent = ToolAgent(
        name='VertexAI Error Handler',
        system_prompt="""You are a helpful assistant that uses external services. 
                        If a service fails, try to provide helpful information about what went wrong.""",
        llm=vertexai_llm,
        tools=[flaky_tool],
        max_retries=3,
    )

    test_queries = [
        'Process this successful query',
        'Process this error query',  # This will trigger the error
    ]

    print('\n=== VertexAI Error Handling ===')
    for query in test_queries:
        print(f'\nQuery: {query}')
        try:
            response = await agent.run(query)
            print(f'Response: {response}')
        except AgentError as e:
            print(f'Agent error: {str(e)}')
            if e.original_error:
                print(f'Original error: {str(e.original_error)}')
        except Exception as e:
            print(f'Unexpected error: {e}')
        print('-' * 80)


async def main():
    """Main function to run all VertexAI examples"""

    # Check for required environment variables
    project = os.getenv('GOOGLE_CLOUD_PROJECT')
    if not project:
        print('⚠️  GOOGLE_CLOUD_PROJECT environment variable not set.')
        print(
            '   Please set it to your Google Cloud project ID to run VertexAI examples.'
        )
        print('   Example: export GOOGLE_CLOUD_PROJECT=your-project-id')
        return

    print('🚀 Running VertexAI LLM Examples')
    print('=' * 50)

    try:
        # Run conversational example
        await example_vertexai_conversational()

        # Run tool agent example
        await example_vertexai_tool_agent()

        # Run structured output example
        await example_vertexai_structured_output()

        # Run error handling example
        await example_vertexai_error_handling()

        print('\n✅ All VertexAI examples completed successfully!')

    except Exception as e:
        print(f'\n❌ Error running examples: {e}')
        print('\nMake sure you have:')
        print('1. Set GOOGLE_CLOUD_PROJECT environment variable')
        print(
            '2. Configured Google Cloud authentication (gcloud auth application-default login)'
        )
        print('3. Enabled Vertex AI API in your Google Cloud project')
        raise e


if __name__ == '__main__':
    asyncio.run(main())
