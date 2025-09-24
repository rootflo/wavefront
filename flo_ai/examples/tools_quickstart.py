"""
Quick start example demonstrating Flo AI tools functionality.

This example shows:
1. Basic tool creation with @flo_tool decorator
2. Partial tools with pre-filled parameters
3. YAML configuration
4. Tool execution
"""

import asyncio
from flo_ai.tool.flo_tool import flo_tool
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI


# Example 1: Basic tool creation
@flo_tool(
    description='Calculate mathematical expressions',
    parameter_descriptions={
        'expression': 'Mathematical expression to evaluate',
        'precision': 'Number of decimal places for the result',
    },
)
async def calculate(expression: str, precision: int = 2) -> str:
    """Calculate mathematical expressions safely."""
    try:
        # Simple evaluation (in production, use a safer method)
        result = eval(expression)
        return f'Result: {result:.{precision}f}'
    except Exception as e:
        return f'Error: {str(e)}'


# Example 2: Tool with multiple parameters (for partial tool demo)
@flo_tool(
    description='Query a database',
    parameter_descriptions={
        'query': 'SQL query to execute',
        'database_url': 'Database connection URL',
        'timeout': 'Query timeout in seconds',
        'max_rows': 'Maximum number of rows to return',
    },
)
async def query_database(
    query: str, database_url: str, timeout: int = 30, max_rows: int = 1000
) -> str:
    """Execute a database query."""
    return f"Executed query '{query}' on {database_url} (timeout: {timeout}s, max_rows: {max_rows})"


# Example 3: Web search tool
@flo_tool(
    description='Search the web for information',
    parameter_descriptions={
        'query': 'Search query',
        'max_results': 'Maximum number of results',
        'language': 'Language for search results',
    },
)
async def web_search(query: str, max_results: int = 10, language: str = 'en') -> str:
    """Search the web for information."""
    return f"Found {max_results} results for '{query}' in {language}"


async def main():
    """Demonstrate tools functionality."""
    print('=== Flo AI Tools Quick Start ===\n')

    # 1. Basic tool usage
    print('1. Basic tool usage...')
    result = await calculate('2 + 3 * 4', precision=1)
    print(f'Calculation result: {result}')
    print()

    # 2. Show tool properties
    print('2. Tool properties...')
    print(f'Tool name: {calculate.tool.name}')
    print(f'Tool description: {calculate.tool.description}')
    print(f'Tool parameters: {list(calculate.tool.parameters.keys())}')
    for param, info in calculate.tool.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")
    print()

    # 3. Partial tool demonstration
    print('3. Partial tool demonstration...')

    # Create agent with partial tools
    agent = (
        AgentBuilder()
        .with_name('Data Analyst Assistant')
        .with_prompt('You are a data analyst. Use the provided tools to analyze data.')
        .with_llm(OpenAI(model='gpt-4'))
        .add_tool(calculate.tool)  # Regular tool
        .add_tool(
            query_database.tool,
            database_url='postgresql://prod-db.company.com:5432/analytics',
            timeout=60,
            max_rows=5000,
        )  # Partial tool with pre-filled parameters
        .add_tool(
            web_search.tool, max_results=5, language='en'
        )  # Partial tool with pre-filled parameters
        .build()
    )

    print(f'Agent created with {len(agent.tools)} tools')
    print('Tools available to AI:')
    for i, tool in enumerate(agent.tools):
        print(f'  {i+1}. {tool.name}: {list(tool.parameters.keys())}')
    print()

    # 4. Demonstrate parameter filtering
    print('4. Parameter filtering demonstration...')

    # Original tool parameters (all visible)
    print('Original database tool parameters:')
    for param, info in query_database.tool.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")

    # Partial tool parameters (filtered)
    partial_tool = agent.tools[1]  # The query_database tool
    print('\nPartial database tool parameters (AI view):')
    for param, info in partial_tool.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")

    # Show pre-filled parameters
    if hasattr(partial_tool, 'get_pre_filled_params'):
        print(
            f'\nPre-filled parameters (hidden from AI): {partial_tool.get_pre_filled_params()}'
        )
    print()

    # 5. Tool execution demonstration
    print('5. Tool execution demonstration...')

    # Execute the partial tool (AI only needs to provide query)
    try:
        result = await partial_tool.execute(
            query='SELECT COUNT(*) FROM users WHERE active = true'
        )
        print(f'Database query result: {result}')
    except Exception as e:
        print(f'Error executing tool: {e}')
    print()

    # 6. YAML configuration example
    print('6. YAML configuration example...')

    yaml_config = """
agent:
  name: "YAML Configured Agent"
  job: "You are an agent configured via YAML."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "calculate"
    - name: "query_database"
      pre_filled_params:
        database_url: "postgresql://yaml-db.company.com:5432/data"
        timeout: 45
        max_rows: 2000
      name_override: "query_yaml_database"
      description_override: "Query YAML-configured database"
    - name: "web_search"
      pre_filled_params:
        max_results: 3
        language: "en"
      name_override: "search_web"
      description_override: "Search the web for information"
"""

    # Create tool registry
    tool_registry = {
        'calculate': calculate.tool,
        'query_database': query_database.tool,
        'web_search': web_search.tool,
    }

    try:
        yaml_agent = AgentBuilder.from_yaml(yaml_config, tool_registry=tool_registry)
        print(f'YAML agent created: {yaml_agent._name}')
        print(f'YAML agent tools: {[tool.name for tool in yaml_agent._tools]}')
    except Exception as e:
        print(f'Error creating YAML agent (expected - no API key): {e}')
    print()

    # 7. Tool parameter management
    print('7. Tool parameter management...')

    if hasattr(partial_tool, 'add_pre_filled_param'):
        # Add a new pre-filled parameter
        partial_tool.add_pre_filled_param('retry_count', 3)
        print(f'Added retry_count parameter: {partial_tool.get_pre_filled_params()}')

        # Remove a parameter
        partial_tool.remove_pre_filled_param('retry_count')
        print(f'Removed retry_count parameter: {partial_tool.get_pre_filled_params()}')
    print()

    print('=== Quick Start Complete ===')
    print('For more detailed documentation, see TOOLS.md')


if __name__ == '__main__':
    asyncio.run(main())
