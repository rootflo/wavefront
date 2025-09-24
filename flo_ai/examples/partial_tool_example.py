"""
Example demonstrating partial tool functionality.

This example shows how to create tools with pre-filled parameters
that are hidden from the AI, allowing for cleaner agent interactions.
"""

import asyncio
from flo_ai.tool.flo_tool import flo_tool
from flo_ai.tool.partial_tool import create_partial_tool
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI


# Example 1: BigQuery tool with datasource configuration
@flo_tool(
    description='Query BigQuery database',
    parameter_descriptions={
        'query': 'SQL query to execute',
        'datasource_id': 'ID of the data source',
        'project_id': 'Google Cloud project ID',
        'dataset': 'BigQuery dataset name',
    },
)
async def bigquery_query(
    query: str, datasource_id: str, project_id: str, dataset: str
) -> str:
    """Execute a BigQuery query."""
    # Simulate BigQuery execution
    return f"Executed query '{query}' on {project_id}.{dataset} using datasource {datasource_id}"


# Example 2: Web search tool with configuration
@flo_tool(
    description='Search the web for information',
    parameter_descriptions={
        'query': 'Search query',
        'max_results': 'Maximum number of results to return',
        'language': 'Language for search results',
    },
)
async def web_search(query: str, max_results: int = 10, language: str = 'en') -> str:
    """Search the web for information."""
    # Simulate web search
    return f"Found {max_results} results for '{query}' in {language}"


# Example 3: Calculator tool (standalone, no pre-filling needed)
@flo_tool(
    description='Perform mathematical calculations',
    parameter_descriptions={'expression': 'Mathematical expression to evaluate'},
)
async def calculate(expression: str) -> str:
    """Calculate mathematical expressions."""
    try:
        # Simple evaluation (in production, use a safer method)
        result = eval(expression)
        return f'Result: {result}'
    except Exception as e:
        return f'Error: {str(e)}'


async def main():
    """Demonstrate partial tool usage."""
    print('=== Partial Tool Example ===\n')

    # Create partial tools with pre-filled parameters
    print('1. Creating partial tools with pre-filled parameters...')

    # BigQuery tool with pre-filled datasource info
    bigquery_partial = create_partial_tool(
        bigquery_query.tool,
        datasource_id='ds_analytics_123',
        project_id='my-company-project',
        dataset='user_analytics',
    )

    # Web search tool with pre-filled configuration
    web_search_partial = create_partial_tool(
        web_search.tool, max_results=5, language='en'
    )

    print(
        f'BigQuery partial tool parameters: {list(bigquery_partial.parameters.keys())}'
    )
    print(
        f'Web search partial tool parameters: {list(web_search_partial.parameters.keys())}'
    )
    print()

    # Test the partial tools
    print('2. Testing partial tools...')

    # Test BigQuery partial tool
    bigquery_result = await bigquery_partial.execute(
        query='SELECT COUNT(*) FROM users WHERE active = true'
    )
    print(f'BigQuery result: {bigquery_result}')

    # Test web search partial tool
    web_result = await web_search_partial.execute(
        query='artificial intelligence trends 2024'
    )
    print(f'Web search result: {web_result}')
    print()

    # Create an agent with partial tools using the simplified interface
    print('3. Creating agent with partial tools...')

    agent = (
        AgentBuilder()
        .with_name('Data Analyst Assistant')
        .with_prompt(
            'You are a data analyst. Use the provided tools to analyze data and search for information.'
        )
        .with_llm(OpenAI(model='gpt-4'))
        .with_tools(
            [
                # Tool with pre-filled parameters using dictionary format
                {
                    'tool': bigquery_query.tool,
                    'pre_filled_params': {
                        'datasource_id': 'ds_production_456',
                        'project_id': 'company-prod',
                        'dataset': 'analytics',
                    },
                },
                # Tool with pre-filled parameters using dictionary format
                {
                    'tool': web_search.tool,
                    'pre_filled_params': {'max_results': 3, 'language': 'en'},
                },
                # Regular tool without pre-filling
                calculate.tool,
            ]
        )
        .build()
    )

    print(f'Agent created with {len(agent.tools)} tools')
    print('Tools available to AI:')
    for tool in agent.tools:
        print(f'  - {tool.name}: {list(tool.parameters.keys())}')
    print()

    # Alternative: Using add_tool method for individual tools
    print('4. Alternative: Using add_tool method...')

    agent2 = (
        AgentBuilder()
        .with_name('Simple Assistant')
        .with_prompt('You are a simple assistant.')
        .with_llm(OpenAI(model='gpt-4'))
        .add_tool(calculate.tool)  # Regular tool
        .add_tool(
            bigquery_query.tool,
            datasource_id='ds_simple_789',
            project_id='simple-project',
            dataset='data',
        )  # Tool with pre-filled parameters
        .build()
    )

    print(f'Alternative agent created with {len(agent2.tools)} tools')
    print('Tools available to AI:')
    for tool in agent2.tools:
        print(f'  - {tool.name}: {list(tool.parameters.keys())}')
    print()

    # Demonstrate tool parameter management
    print('5. Demonstrating parameter management...')

    # Add a new pre-filled parameter
    bigquery_partial.add_pre_filled_param('timeout', 30)
    print(f'Added timeout parameter: {bigquery_partial.get_pre_filled_params()}')

    # Remove a parameter
    bigquery_partial.remove_pre_filled_param('timeout')
    print(f'Removed timeout parameter: {bigquery_partial.get_pre_filled_params()}')
    print()

    # Show the difference between original and partial tools
    print('6. Comparing original vs partial tools...')

    print('Original BigQuery tool parameters:')
    for param, info in bigquery_query.tool.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")

    print('\nPartial BigQuery tool parameters (AI view):')
    for param, info in bigquery_partial.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")

    print(
        f'\nPre-filled parameters (hidden from AI): {bigquery_partial.get_pre_filled_params()}'
    )


if __name__ == '__main__':
    asyncio.run(main())
