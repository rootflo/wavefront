import asyncio
from flo_ai.models import TextMessageContent, UserMessage
from flo_ai.models.agent import Agent as ToolAgent
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.tool.base_tool import Tool
from flo_ai.models.agent_error import AgentError
from flo_ai.models.base_agent import ReasoningPattern


# Example of using ToolAgent as a conversational agent
async def test_conversational():
    llm = OpenAI(model='gpt-4', temperature=0.7)
    agent = ToolAgent(
        name='Assistant',
        system_prompt='You are a helpful AI assistant.',
        llm=llm,
    )

    response = await agent.run(
        [UserMessage(content=TextMessageContent(text='What is the capital of France?'))]
    )
    print(response)


# Example of using ToolAgent with tools
async def test_tool_agent():
    # Define a simple tool
    async def get_weather(city: str) -> str:
        # This would normally call a weather API
        return f'The weather in {city} is sunny'

    weather_tool = Tool(
        name='get_weather',
        description='Get the weather for a city',
        function=get_weather,
        parameters={
            'city': {'type': 'string', 'description': 'The city to get weather for'}
        },
    )

    llm = OpenAI(model='gpt-3.5-turbo', temperature=0.7)
    agent = ToolAgent(
        name='WeatherAssistant',
        system_prompt='You are a helpful weather assistant.',
        llm=llm,
        tools=[weather_tool],
    )

    response = await agent.run(
        [
            UserMessage(
                content=TextMessageContent(text="What's the weather like in Paris?")
            )
        ]
    )
    print(response)


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

    llm = OpenAI(model='gpt-3.5-turbo', temperature=0.7)
    agent = ToolAgent(
        name='WeatherAssistant',
        system_prompt='You are a helpful weather assistant.',
        llm=llm,
        tools=[weather_tool],
        max_retries=3,
    )

    try:
        # This will trigger error handling and retries
        response = await agent.run(
            UserMessage(
                content=TextMessageContent(text="What's the weather like in error?")
            )
        )
        print(response)
    except AgentError as e:
        print(f'Agent error: {str(e)}')
        if e.original_error:
            print(f'Original error: {str(e.original_error)}')


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

    llm = OpenAI(model='gpt-3.5-turbo', temperature=0.7)
    agent = ToolAgent(
        name='CalculatorAssistant',
        system_prompt='You are a helpful calculator assistant. Use the calculator tool if needed and answer the question asked.',
        llm=llm,
        tools=[calculator_tool],
        reasoning_pattern=ReasoningPattern.DIRECT,
    )

    response = await agent.run(
        UserMessage(content=TextMessageContent(text='Calculate 5 plus 3'))
    )
    print(response)


# Run the examples
if __name__ == '__main__':
    print('Testing conversational agent...\n')
    asyncio.run(test_conversational())

    print('\nTesting tool agent...\n')
    asyncio.run(test_tool_agent())

    # print('\nTesting error handling...\n')
    # asyncio.run(test_error_handling())

    # print('\nTesting direct reasoning...\n')
    # asyncio.run(test_direct_reasoning())
