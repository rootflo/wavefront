# Tools Documentation

This document provides comprehensive documentation for the Flo AI tools system, including basic tools, partial tools, and YAML configuration.

## Table of Contents

- [Overview](#overview)
- [Basic Tools](#basic-tools)
- [Partial Tools](#partial-tools)
- [Tool Configuration](#tool-configuration)
- [YAML Configuration](#yaml-configuration)
- [Examples](#examples)
- [API Reference](#api-reference)

## Overview

The Flo AI tools system allows you to create and configure tools that can be used by AI agents. Tools can be:

- **Standalone tools**: Simple functions that don't require external context (e.g., calculator, web search)
- **Entity-attached tools**: Tools that require specific context or configuration (e.g., BigQuery with datasource ID, email with SMTP settings)

The system supports:

- Basic tool creation and usage
- Partial tools with pre-filled parameters
- YAML-based tool configuration
- Tool registries for easy management

## Basic Tools

### Creating Tools with @flo_tool Decorator

The `@flo_tool` decorator is the easiest way to create tools:

```python
from flo_ai.tool.flo_tool import flo_tool

@flo_tool(
    description="Calculate mathematical expressions",
    parameter_descriptions={
        "expression": "Mathematical expression to evaluate",
        "precision": "Number of decimal places for the result"
    }
)
async def calculate(expression: str, precision: int = 2) -> str:
    """Calculate mathematical expressions."""
    try:
        result = eval(expression)
        return f"Result: {result:.{precision}f}"
    except Exception as e:
        return f"Error: {str(e)}"

# The tool is automatically available as calculate.tool
```

### Tool Properties

Every tool has these properties:

- `name`: Tool name (defaults to function name)
- `description`: Tool description (defaults to docstring)
- `parameters`: Dictionary of parameter definitions
- `function`: The actual function to execute

### Using Tools in Agents

```python
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI

agent = (AgentBuilder()
    .with_name("Math Assistant")
    .with_prompt("You are a math assistant. Use the calculator tool.")
    .with_llm(OpenAI(model="gpt-4"))
    .add_tool(calculate.tool)
    .build())
```

## Partial Tools

Partial tools allow you to pre-fill some parameters during agent building, hiding them from the AI while still allowing the AI to provide additional parameters.

### Why Use Partial Tools?

**Problem**: Some tools require context-specific parameters that shouldn't be provided by the AI:

- BigQuery tools need `datasource_id` and `project_id`
- Email tools need SMTP server configuration
- Database tools need connection strings

**Solution**: Pre-fill these parameters during agent building, so the AI only sees what it needs to provide.

### Creating Partial Tools

#### Method 1: Using AgentBuilder.add_tool()

```python
from flo_ai.builder.agent_builder import AgentBuilder

# BigQuery tool with multiple parameters
@flo_tool(description="Query BigQuery database")
async def bigquery_query(
    query: str,
    datasource_id: str,
    project_id: str,
    dataset: str
) -> str:
    return f"Executed: {query} on {project_id}.{dataset}"

# Create agent with pre-filled parameters
agent = (AgentBuilder()
    .with_name("Data Analyst")
    .with_prompt("You are a data analyst.")
    .with_llm(OpenAI(model="gpt-4"))
    .add_tool(
        bigquery_query.tool,
        datasource_id="ds_production_123",
        project_id="my-company-prod",
        dataset="analytics"
    )
    .build())

# AI only needs to provide the query parameter
```

#### Method 2: Using Tool Dictionaries

```python
agent = (AgentBuilder()
    .with_name("Data Analyst")
    .with_prompt("You are a data analyst.")
    .with_llm(OpenAI(model="gpt-4"))
    .with_tools([
        {
            "tool": bigquery_query.tool,
            "prefilled_params": {
                "datasource_id": "ds_production_123",
                "project_id": "my-company-prod",
                "dataset": "analytics"
            },
            "name_override": "query_production_data",
            "description_override": "Query production BigQuery data"
        }
    ])
    .build())
```

#### Method 3: Using ToolConfig Class

```python
from flo_ai.tool.tool_config import ToolConfig, create_tool_config

# Create partial tool configuration
partial_tool = create_tool_config(
    bigquery_query.tool,
    datasource_id="ds_production_123",
    project_id="my-company-prod",
    dataset="analytics"
)

agent = (AgentBuilder()
    .with_name("Data Analyst")
    .with_prompt("You are a data analyst.")
    .with_llm(OpenAI(model="gpt-4"))
    .with_tools([partial_tool])
    .build())
```

### How Partial Tools Work

1. **Parameter Filtering**: Pre-filled parameters are completely hidden from the AI
2. **Automatic Merging**: During execution, pre-filled parameters are merged with AI-provided parameters
3. **AI Override**: If the AI provides a parameter that's pre-filled, the AI's value takes precedence

```python
# Original tool parameters (AI sees all)
bigquery_query.tool.parameters
# {'query': {...}, 'datasource_id': {...}, 'project_id': {...}, 'dataset': {...}}

# Partial tool parameters (AI only sees non-pre-filled)
partial_tool.parameters
# {'query': {...}}  # Only query is visible to AI

# During execution, parameters are merged:
# AI provides: {"query": "SELECT * FROM users"}
# Final call: {"query": "SELECT * FROM users", "datasource_id": "ds_123", ...}
```

## Tool Configuration

### ToolConfig Class

The `ToolConfig` class provides a flexible way to configure tools:

```python
from flo_ai.tool.tool_config import ToolConfig

tool_config = ToolConfig(
    tool=my_tool,
    prefilled_params={"param1": "value1", "param2": "value2"},
    name_override="custom_tool_name",
    description_override="Custom tool description"
)

# Convert to tool
configured_tool = tool_config.to_tool()
```

### ToolConfig Methods

- `is_partial()`: Check if the tool has pre-filled parameters
- `to_tool()`: Convert configuration to a Tool object
- `get_prefilled_params()`: Get pre-filled parameters

## YAML Configuration

YAML configuration allows you to define tools and their configurations in YAML files, making it easy to manage different environments and configurations.

### Basic YAML Structure

```yaml
agent:
  name: "Data Analyst Assistant"
  job: "You are a data analyst with access to BigQuery and web search tools."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    # Simple tool reference
    - "calculate"

    # Tool with pre-filled parameters
    - name: "bigquery_query"
      prefilled_params:
        datasource_id: "ds_production_123"
        project_id: "my-company-prod"
        dataset: "analytics"
      name_override: "query_production_data"
      description_override: "Query production BigQuery data"

    # Tool with different configuration
    - name: "web_search"
      prefilled_params:
        max_results: 5
        language: "en"
      name_override: "search_web"
      description_override: "Search the web for information"
```

### Environment-Specific Configurations

#### Production Configuration (`agent_config.yaml`)

```yaml
agent:
  name: "Production Data Analyst"
  job: "You are a data analyst working with production data."
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

    - name: "send_email"
      prefilled_params:
        smtp_server: "smtp.company.com"
        smtp_port: 587
      name_override: "send_notification"
      description_override: "Send email notifications"
```

#### Development Configuration (`agent_config_dev.yaml`)

```yaml
agent:
  name: "Development Data Analyst"
  job: "You are a data analyst working with test data."
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
```

### Using YAML Configuration

```python
from flo_ai.builder.agent_builder import AgentBuilder

# Create tool registry
tool_registry = {
    "bigquery_query": bigquery_query.tool,
    "web_search": web_search.tool,
    "calculate": calculate.tool,
    "send_email": send_email.tool,
}

# Load from YAML
with open("agent_config.yaml", "r") as f:
    yaml_str = f.read()

agent = AgentBuilder.from_yaml(
    yaml_str,
    tool_registry=tool_registry
)
```

## Examples

### Complete Example: Data Analyst Agent

```python
import asyncio
from flo_ai.tool.flo_tool import flo_tool
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI

# Define tools
@flo_tool(description="Query BigQuery database")
async def bigquery_query(
    query: str,
    datasource_id: str,
    project_id: str,
    dataset: str
) -> str:
    return f"Executed: {query} on {project_id}.{dataset}"

@flo_tool(description="Search the web")
async def web_search(query: str, max_results: int = 10) -> str:
    return f"Found {max_results} results for: {query}"

@flo_tool(description="Calculate mathematical expressions")
async def calculate(expression: str) -> str:
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"

# Create agent with partial tools
agent = (AgentBuilder()
    .with_name("Data Analyst")
    .with_prompt("You are a data analyst. Use the provided tools to analyze data.")
    .with_llm(OpenAI(model="gpt-4"))
    .add_tool(calculate.tool)  # Regular tool
    .add_tool(
        bigquery_query.tool,
        datasource_id="ds_production_123",
        project_id="my-company-prod",
        dataset="analytics"
    )  # Partial tool
    .add_tool(
        web_search.tool,
        max_results=5
    )  # Partial tool
    .build())

# Test the agent
async def test_agent():
    # The AI only needs to provide the query for BigQuery
    # datasource_id, project_id, and dataset are pre-filled
    result = await agent.tools[1].execute(query="SELECT COUNT(*) FROM users")
    print(result)  # "Executed: SELECT COUNT(*) FROM users on my-company-prod.analytics"

asyncio.run(test_agent())
```

### YAML Example

```yaml
# agent_config.yaml
agent:
  name: "Data Analyst Assistant"
  job: "You are a data analyst with access to BigQuery and web search tools."
  model:
    provider: "openai"
    name: "gpt-4"
  tools:
    - "calculate"
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
  settings:
    temperature: 0.7
    max_retries: 3
    reasoning_pattern: "DIRECT"
```

```python
# Load from YAML
tool_registry = {
    "bigquery_query": bigquery_query.tool,
    "web_search": web_search.tool,
    "calculate": calculate.tool,
}

with open("agent_config.yaml", "r") as f:
    yaml_str = f.read()

agent = AgentBuilder.from_yaml(
    yaml_str,
    tool_registry=tool_registry
)
```

## API Reference

### @flo_tool Decorator

```python
@flo_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameter_descriptions: Optional[Dict[str, str]] = None
)
```

**Parameters:**

- `name`: Custom name for the tool (defaults to function name)
- `description`: Tool description (defaults to function docstring)
- `parameter_descriptions`: Dict mapping parameter names to descriptions

### ToolConfig Class

```python
class ToolConfig:
    def __init__(
        self,
        tool: Tool,
        prefilled_params: Optional[Dict[str, Any]] = None,
        name_override: Optional[str] = None,
        description_override: Optional[str] = None,
    )
```

**Methods:**

- `is_partial() -> bool`: Check if tool has pre-filled parameters
- `to_tool() -> Tool`: Convert to Tool object
- `get_prefilled_params() -> Dict[str, Any]`: Get pre-filled parameters

### PartialTool Class

```python
class PartialTool(Tool):
    def __init__(
        self,
        base_tool: Tool,
        prefilled_params: Dict[str, Any],
        name_override: Optional[str] = None,
        description_override: Optional[str] = None,
    )
```

**Methods:**

- `get_original_tool() -> Tool`: Get the original tool
- `get_prefilled_params() -> Dict[str, Any]`: Get pre-filled parameters
- `add_prefilled_param(key: str, value: Any) -> PartialTool`: Add parameter
- `remove_prefilled_param(key: str) -> PartialTool`: Remove parameter

### AgentBuilder Methods

```python
# Add single tool with optional pre-filled parameters
def add_tool(self, tool: Tool, **prefilled_params) -> 'AgentBuilder'

# Add multiple tools (supports Tool, ToolConfig, or dict)
def with_tools(self, tools: Union[List[Tool], List[ToolConfig], List[Dict[str, Any]]]) -> 'AgentBuilder'

# Load from YAML
@classmethod
def from_yaml(
    cls,
    yaml_str: str,
    tools: Optional[List[Tool]] = None,
    base_llm: Optional[BaseLLM] = None,
    tool_registry: Optional[Dict[str, Tool]] = None,
) -> 'AgentBuilder'
```

## Best Practices

### 1. Tool Design

- **Single Responsibility**: Each tool should have one clear purpose
- **Clear Parameters**: Use descriptive parameter names and descriptions
- **Error Handling**: Always handle errors gracefully
- **Type Hints**: Use type hints for better documentation

### 2. Partial Tools

- **Pre-fill Context**: Pre-fill parameters that are environment-specific
- **Hide Complexity**: Hide technical details from the AI
- **Consistent Naming**: Use consistent naming for pre-filled parameters

### 3. YAML Configuration

- **Environment Separation**: Use different YAML files for different environments
- **Tool Registry**: Maintain a centralized tool registry
- **Version Control**: Keep YAML files in version control
- **Documentation**: Document tool configurations

### 4. Error Handling

```python
@flo_tool(description="Query database")
async def query_database(query: str, connection_string: str) -> str:
    try:
        # Database query logic
        return result
    except Exception as e:
        return f"Database error: {str(e)}"
```

### 5. Testing

```python
import pytest
from unittest.mock import Mock, AsyncMock

def test_tool_execution():
    mock_function = AsyncMock(return_value="test_result")
    tool = Tool(
        name="test_tool",
        description="A test tool",
        function=mock_function,
        parameters={"param1": {"type": "string", "description": "Param 1", "required": True}}
    )

    result = await tool.execute(param1="test_value")
    assert result == "test_result"
    mock_function.assert_called_once_with(param1="test_value")
```

## Troubleshooting

### Common Issues

1. **Tool not found in registry**: Ensure the tool is registered with the correct name
2. **Parameter validation errors**: Check that all required parameters are provided
3. **YAML parsing errors**: Validate YAML syntax and structure
4. **Import errors**: Ensure all required modules are imported

### Debug Tips

1. **Check tool parameters**: Use `tool.parameters` to see what the AI sees
2. **Verify pre-filled params**: Use `partial_tool.get_prefilled_params()`
3. **Test tool execution**: Test tools independently before using in agents
4. **Check YAML structure**: Validate YAML with online validators

## Migration Guide

### From Basic Tools to Partial Tools

```python
# Before: AI needs to provide all parameters
agent.add_tool(bigquery_query.tool)

# After: Pre-fill context-specific parameters
agent.add_tool(
    bigquery_query.tool,
    datasource_id="ds_123",
    project_id="my-project"
)
```

### From Code to YAML Configuration

```python
# Before: Hard-coded in code
agent = (AgentBuilder()
    .with_name("Data Analyst")
    .with_prompt("You are a data analyst.")
    .with_llm(OpenAI(model="gpt-4"))
    .add_tool(bigquery_query.tool)
    .build())

# After: YAML configuration
agent = AgentBuilder.from_yaml(yaml_str, tool_registry=tool_registry)
```

This documentation covers all aspects of the Flo AI tools system. For more specific examples, see the `examples/` directory in the repository.
