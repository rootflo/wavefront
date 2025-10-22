"""
Example demonstrating OpenTelemetry integration with flo_ai

This example shows how to:
1. Configure telemetry with OTLP and console exporters
2. Track LLM calls with token usage
3. Monitor agent execution with performance metrics
4. Track workflow execution in Arium

Requirements:
- OpenTelemetry collector running (optional, for OTLP export)
- Or use console export for debugging
"""

import asyncio
import os
from flo_ai import (
    Agent,
    OpenAI,
    configure_telemetry,
    shutdown_telemetry,
    flo_tool,
    AriumBuilder,
    MessageMemory,
)


# Configure telemetry at the start of your application
def setup_telemetry():
    """
    Configure OpenTelemetry for the application

    Options:
    1. Console export (for debugging) - set console_export=True
    2. OTLP export (for production) - provide otlp_endpoint
    3. Both - set both options

    Environment variables:
    - FLO_ENV: Environment name (development, staging, production)
    - FLO_OTLP_ENDPOINT: OTLP collector endpoint (e.g., http://localhost:4317)
    """
    configure_telemetry(
        service_name='flo_ai_example',
        service_version='1.0.0',
        environment=os.getenv('FLO_ENV', 'development'),
        # For local testing with Jaeger/OTLP collector:
        otlp_endpoint='http://localhost:4317',
        # For debugging, export to console:
        console_export=True,
        additional_attributes={
            'deployment.region': 'us-west-2',
            'service.instance.id': 'instance-1',
        },
    )
    print('✓ Telemetry configured')


# Example 1: Basic Agent with LLM Telemetry
async def example_basic_agent(llm):
    """
    Demonstrates basic agent with automatic LLM telemetry.

    Telemetry captured:
    - LLM request duration
    - Token usage (prompt, completion, total)
    - Agent execution time
    - Success/error metrics
    """
    print('\n=== Example 1: Basic Agent with Telemetry ===')

    # Create an agent (telemetry is automatically tracked)
    agent = Agent(
        name='researcher',
        system_prompt='You are a helpful research assistant.',
        llm=llm,
    )

    # Run the agent - all metrics are automatically captured
    response = await agent.run('What is the capital of France?')
    print(f'Response: {response}')

    return response


# Example 2: Agent with Tools
async def example_agent_with_tools(llm):
    """
    Demonstrates agent with tool calls and telemetry.

    Telemetry captured:
    - Tool execution duration
    - Tool success/failure rates
    - Number of tool calls per agent run
    """
    print('\n=== Example 2: Agent with Tools ===')

    # Define a simple tool
    @flo_tool(
        name='calculator',
        description='Performs basic arithmetic operations',
    )
    async def calculator(operation: str, a: float, b: float) -> float:
        """
        Perform calculation

        Args:
            operation: One of 'add', 'subtract', 'multiply', 'divide'
            a: First number
            b: Second number

        Returns:
            Result of the operation
        """
        if operation == 'add':
            return a + b
        elif operation == 'subtract':
            return a - b
        elif operation == 'multiply':
            return a * b
        elif operation == 'divide':
            return a / b if b != 0 else 0
        else:
            raise ValueError(f'Unknown operation: {operation}')

    agent = Agent(
        name='calculator_agent',
        system_prompt='You are a helpful calculator assistant. Use the calculator tool to perform calculations.',
        llm=llm,
        tools=[
            calculator.tool
        ],  # Access the .tool attribute from the decorated function
    )

    # Run with tool calls - tool metrics are automatically captured
    response = await agent.run('What is 25 multiplied by 4, then add 10?')
    print(f'Response: {response}')

    return response


# Example 3: Workflow with Arium
async def example_workflow(llm):
    """
    Demonstrates workflow telemetry with Arium.

    Telemetry captured:
    - Workflow execution duration
    - Individual node execution times
    - Node success/failure rates
    - Workflow traversal paths
    """
    print('\n=== Example 3: Workflow Telemetry ===')

    # Create agents
    researcher = Agent(
        name='researcher',
        system_prompt='You are a research assistant. Provide concise, factual information.',
        llm=llm,
    )

    summarizer = Agent(
        name='summarizer',
        system_prompt='You are a summarization expert. Create brief, clear summaries.',
        llm=llm,
    )

    # Build workflow
    builder = (
        AriumBuilder()
        .with_memory(MessageMemory())
        .add_agent(researcher)
        .add_agent(summarizer)
        .start_with(researcher)
        .connect(researcher, summarizer)
        .end_with(summarizer)
    )

    # Compile and set name for telemetry
    workflow = builder.build()
    workflow.name = 'research_workflow'  # This name will appear in telemetry

    # Run workflow - all node executions are tracked
    result = await workflow.run(inputs=['What are the key benefits of OpenTelemetry?'])

    print(f'Workflow result: {result}')
    return result


# Example 4: Multiple LLM Providers
async def example_multiple_providers(llm):
    """
    Demonstrates telemetry across different LLM providers.

    Telemetry will show:
    - Performance comparison between providers
    - Token usage by provider
    - Error rates by provider
    """
    print('\n=== Example 4: Multiple LLM Providers ===')

    agent = Agent(
        name='test_agent',
        system_prompt='You are a helpful assistant.',
        llm=llm,
    )

    question = 'What is 2+2?'

    print(f'Testing {llm.__class__.__name__}...')
    response = await agent.run(question)
    print(f'Response: {response}')

    # Telemetry will show metrics grouped by provider


# Example 5: Streaming Telemetry
async def example_streaming_telemetry(llm):
    """
    Demonstrates telemetry for streaming LLM calls.

    Telemetry captured:
    - Stream request duration
    - Number of chunks received
    - Stream success/error rates
    - Streaming-specific metrics
    """
    print('\n=== Example 5: Streaming Telemetry ===')

    # Test streaming with telemetry
    messages = [
        {
            'role': 'user',
            'content': 'Tell me a short story about a robot learning to paint.',
        }
    ]

    print('Streaming response with telemetry...')
    full_response = ''
    async for chunk in llm.stream(messages):
        content = chunk.get('content', '')
        if content:
            full_response += content
            print(content, end='', flush=True)

    print(f'\n\nFull response length: {len(full_response)} characters')
    print('✓ Streaming telemetry captured (check your telemetry backend)')

    return full_response


# Example 6: Error Tracking
async def example_error_tracking(llm):
    """
    Demonstrates how errors are tracked in telemetry.

    Telemetry captured:
    - Error types and counts
    - Retry attempts
    - Failed operations with context
    """
    print('\n=== Example 6: Error Tracking ===')

    # Create a tool that might fail
    @flo_tool(
        name='risky_operation',
        description='An operation that might fail',
    )
    async def risky_operation(value: int) -> str:
        if value < 0:
            raise ValueError('Value must be non-negative')
        return f'Success with value: {value}'

    agent = Agent(
        name='error_test_agent',
        system_prompt='You are a testing assistant.',
        llm=llm,
        tools=[
            risky_operation.tool
        ],  # Access the .tool attribute from the decorated function
        max_retries=2,
    )

    try:
        # This might cause errors that will be tracked
        response = await agent.run('Use the risky_operation with value -5')
        print(f'Response: {response}')
    except Exception as e:
        print(f'Caught error (tracked in telemetry): {e}')


async def main(llm=None):
    """Main function to run all examples

    Args:
        llm: LLM instance to use for all examples. If None, defaults to OpenAI.
    """
    # 1. Configure telemetry first
    setup_telemetry()

    # Use provided LLM or default to OpenAI
    if llm is None:
        llm = OpenAI(model='gpt-4o-mini')

    try:
        # 2. Run examples with the provided LLM
        await example_basic_agent(llm)
        await example_agent_with_tools(llm)
        await example_workflow(llm)
        await example_multiple_providers(llm)
        await example_streaming_telemetry(llm)
        await example_error_tracking(llm)

        print('\n✓ All examples completed')
        print('\n=== Telemetry Data ===')
        print('Metrics collected:')
        print('- LLM request counts, latencies, token usage')
        print('- LLM streaming: chunks received, stream duration, success rates')
        print('- Agent execution times, tool calls, retries')
        print('- Workflow execution times, node traversals')
        print('- Error rates and types')

    finally:
        # 3. Shutdown telemetry to flush all data
        print('\nShutting down telemetry...')
        shutdown_telemetry()
        print('✓ Telemetry shutdown complete')


# Running with Jaeger (optional)
"""
To visualize telemetry data with Jaeger:

1. Start Jaeger (using Docker):
   docker run -d --name jaeger \
     -e COLLECTOR_OTLP_ENABLED=true \
     -p 16686:16686 \
     -p 4317:4317 \
     jaegertracing/all-in-one:latest

2. Update the configure_telemetry call to use OTLP:
   configure_telemetry(
       service_name="flo_ai_example",
       otlp_endpoint="http://localhost:4317",
       console_export=False
   )

3. Run this script

4. View traces at http://localhost:16686

Alternatively, use Grafana, Prometheus, or any OpenTelemetry-compatible backend.
"""


if __name__ == '__main__':
    # Set your API keys
    # os.environ["OPENAI_API_KEY"] = "your-key-here"
    # os.environ["GOOGLE_API_KEY"] = "your-key-here"
    # os.environ["ANTHROPIC_API_KEY"] = "your-key-here"

    # Example 1: Run with default OpenAI
    # print("=== Running with OpenAI ===")
    # asyncio.run(main())

    # Example 2: Run with a specific LLM provider
    # Uncomment the provider you want to test:

    from flo_ai import Gemini

    print('\n=== Running with Gemini ===')
    gemini_llm = Gemini(model='gemini-2.5-flash')
    asyncio.run(main(gemini_llm))

    # from flo_ai import Anthropic
    # print("\n=== Running with Anthropic ===")
    # anthropic_llm = Anthropic(model="claude-3-5-sonnet-20241022")
    # asyncio.run(main(anthropic_llm))

    # from flo_ai import OpenAI
    # print("\n=== Running with different OpenAI model ===")
    # openai_llm = OpenAI(model="gpt-4o")
    # asyncio.run(main(openai_llm))
