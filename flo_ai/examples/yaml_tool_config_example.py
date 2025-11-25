"""
Example demonstrating YAML tool configuration with pre-filled parameters.

This example shows how to configure agents with tools that have pre-filled
parameters using YAML configuration files.
"""

import asyncio
from flo_ai.tool.flo_tool import flo_tool
from flo_ai.builder.agent_builder import AgentBuilder


# Define some example tools
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
    return f"Executed query '{query}' on {project_id}.{dataset} using datasource {datasource_id}"


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
    return f"Found {max_results} results for '{query}' in {language}"


@flo_tool(
    description='Perform mathematical calculations',
    parameter_descriptions={'expression': 'Mathematical expression to evaluate'},
)
async def calculate(expression: str) -> str:
    """Calculate mathematical expressions."""
    try:
        result = eval(expression)
        return f'Result: {result}'
    except Exception as e:
        return f'Error: {str(e)}'


@flo_tool(
    description='Send email notifications',
    parameter_descriptions={
        'to': 'Recipient email address',
        'subject': 'Email subject',
        'body': 'Email body content',
        'smtp_server': 'SMTP server address',
        'smtp_port': 'SMTP server port',
    },
)
async def send_email(
    to: str, subject: str, body: str, smtp_server: str, smtp_port: int
) -> str:
    """Send an email notification."""
    return f"Email sent to {to} with subject '{subject}' via {smtp_server}:{smtp_port}"


async def main():
    """Demonstrate YAML tool configuration."""
    print('=== YAML Tool Configuration Example ===\n')

    # Create a tool registry
    tool_registry = {
        'bigquery_query': bigquery_query.tool,
        'web_search': web_search.tool,
        'calculate': calculate.tool,
        'send_email': send_email.tool,
    }

    # Example 1: Simple YAML with tool references
    print('1. Simple YAML with tool references...')
    simple_yaml = """
agent:
  name: "Simple Data Analyst"
  job: "You are a data analyst. Use the provided tools to analyze data."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "calculate"
    - "web_search"
"""

    try:
        agent1 = AgentBuilder.from_yaml(simple_yaml, tool_registry=tool_registry)
        print(f'Created agent: {agent1._name}')
        print(f'Tools: {[tool.name for tool in agent1._tools]}')
    except Exception as e:
        print(f'Error (expected - no API key): {e}')
    print()

    # Example 2: YAML with tool configurations and pre-filled parameters
    print('2. YAML with tool configurations and pre-filled parameters...')
    config_yaml = """
agent:
  name: "Advanced Data Analyst"
  job: "You are an advanced data analyst with access to BigQuery and web search."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - name: "bigquery_query"
      prefilled_params:
        datasource_id: "ds_production_123"
        project_id: "my-company-prod"
        dataset: "analytics"
      name_override: "query_production_data"
      description_override: "Query production BigQuery data"
    
    - name: "web_search"
      prefilled_params:
        max_results: 5
        language: "en"
      name_override: "search_web"
      description_override: "Search the web for information"
    
    - name: "send_email"
      prefilled_params:
        smtp_server: "smtp.company.com"
        smtp_port: 587
      name_override: "send_notification"
      description_override: "Send email notifications"
    
    - "calculate"  # Regular tool without pre-filling
"""

    try:
        agent2 = AgentBuilder.from_yaml(config_yaml, tool_registry=tool_registry)
        print(f'Created agent: {agent2._name}')
        print('Tools available to AI:')
        for tool in agent2._tools:
            print(f'  - {tool.name}: {list(tool.parameters.keys())}')
    except Exception as e:
        print(f'Error (expected - no API key): {e}')
    print()

    # Example 3: Environment-specific configurations
    print('3. Environment-specific configurations...')
    dev_yaml = """
agent:
  name: "Development Data Analyst"
  job: "You are a data analyst working in the development environment."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - name: "bigquery_query"
      prefilled_params:
        datasource_id: "ds_dev_456"
        project_id: "my-company-dev"
        dataset: "test_data"
      name_override: "query_dev_data"
      description_override: "Query development BigQuery data"
    
    - name: "web_search"
      prefilled_params:
        max_results: 3
        language: "en"
      name_override: "search_web"
      description_override: "Search the web for information"
"""

    try:
        agent3 = AgentBuilder.from_yaml(dev_yaml, tool_registry=tool_registry)
        print(f'Created agent: {agent3._name}')
        print('Tools available to AI:')
        for tool in agent3._tools:
            print(f'  - {tool.name}: {list(tool.parameters.keys())}')
    except Exception as e:
        print(f'Error (expected - no API key): {e}')
    print()

    # Example 4: Mixed tool types
    print('4. Mixed tool types...')
    mixed_yaml = """
agent:
  name: "Mixed Tool Agent"
  job: "You are an agent with mixed tool configurations."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "calculate"  # Simple reference
    
    - name: "bigquery_query"
      prefilled_params:
        datasource_id: "ds_mixed_789"
        project_id: "mixed-project"
        dataset: "mixed_data"
    
    - name: "web_search"
      prefilled_params:
        max_results: 10
        language: "en"
      name_override: "search_web"
      description_override: "Search the web for information"
"""

    try:
        agent4 = AgentBuilder.from_yaml(mixed_yaml, tool_registry=tool_registry)
        print(f'Created agent: {agent4._name}')
        print('Tools available to AI:')
        for tool in agent4._tools:
            print(f'  - {tool.name}: {list(tool.parameters.keys())}')
    except Exception as e:
        print(f'Error (expected - no API key): {e}')
    print()

    # Example 5: Show the difference between original and configured tools
    print('5. Comparing original vs configured tools...')

    # Create a tool with pre-filled parameters
    configured_tool = tool_registry['bigquery_query']

    print('Original BigQuery tool parameters:')
    for param, info in configured_tool.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")

    print('\nConfigured BigQuery tool parameters (AI view):')
    # This would be the tool as seen by the AI after YAML configuration
    # In practice, this would be created by the YAML processing
    from flo_ai.tool.tool_config import ToolConfig

    tool_config = ToolConfig(
        tool=configured_tool,
        prefilled_params={
            'datasource_id': 'ds_production_123',
            'project_id': 'my-company-prod',
            'dataset': 'analytics',
        },
    )
    configured_tool_for_ai = tool_config.to_tool()

    for param, info in configured_tool_for_ai.parameters.items():
        print(f"  - {param}: {info['type']} (required: {info['required']})")

    print(f'\nPre-filled parameters (hidden from AI): {tool_config.prefilled_params}')


if __name__ == '__main__':
    asyncio.run(main())
