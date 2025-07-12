# @flo_tool Decorator

The `@flo_tool` decorator is a powerful utility that automatically converts any Python function into a `Tool` object for use with Flo AI agents. It extracts function parameters, type hints, and descriptions to create a fully functional tool with minimal boilerplate code.

## Features

- **Automatic parameter extraction**: Uses Python's `inspect` module to extract function parameters and type hints
- **Flexible descriptions**: Supports custom descriptions, docstring extraction, and parameter-specific descriptions
- **Type conversion**: Automatically converts Python types to JSON schema types
- **Dual functionality**: Functions can be called normally AND used as tools
- **Async support**: Works seamlessly with both sync and async functions

## Basic Usage

### Simple Decorator

```python
from flo_ai.tool import flo_tool

@flo_tool()
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

# Function can be called normally
result = await calculate("add", 5, 3)  # Returns 8

# Tool object is accessible via .tool attribute
tool = calculate.tool
print(tool.name)  # "calculate"
print(tool.description)  # Uses function docstring
print(tool.parameters)  # Automatically extracted from type hints
```

### With Custom Descriptions

```python
@flo_tool(
    name="weather_checker",
    description="Get current weather information for a city",
    parameter_descriptions={
        "city": "The city to get weather for",
        "country": "The country (optional)",
    }
)
async def get_weather(city: str, country: str = None) -> str:
    """Get weather information for a specific city."""
    # Implementation here
    return f"Weather in {city}: sunny"
```

### Using Docstrings for Descriptions

```python
@flo_tool()
async def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert between different units (km/miles, kg/lbs, celsius/fahrenheit).
    
    Args:
        value: The value to convert
        from_unit: The unit to convert from
        to_unit: The unit to convert to
    """
    # Implementation here
    return f"{value} {from_unit} = {result} {to_unit}"
```

## Advanced Usage

### Creating Tools from Existing Functions

If you have existing functions that you want to convert to tools without modifying them:

```python
from flo_ai.tool import create_tool_from_function

async def existing_function(text: str, style: str = "normal") -> str:
    """Format text in different styles."""
    styles = {
        "uppercase": text.upper(),
        "lowercase": text.lower(),
        "title": text.title(),
        "normal": text
    }
    return styles.get(style, text)

# Convert to tool
format_tool = create_tool_from_function(
    existing_function,
    name="text_formatter",
    description="Format text in different styles",
    parameter_descriptions={
        "text": "The text to format",
        "style": "The formatting style (uppercase, lowercase, title, normal)"
    }
)
```

### Using with Agents

```python
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.models.base_agent import ReasoningPattern

# Create tools from decorated functions
tools = [
    calculate.tool,
    get_weather.tool,
    convert_units.tool,
    format_tool  # From create_tool_from_function
]

# Build agent with tools
agent = (
    AgentBuilder()
    .with_name("Multi-Tool Agent")
    .with_prompt("You are a helpful assistant with access to various tools.")
    .with_llm(llm)
    .with_tools(tools)
    .with_reasoning(ReasoningPattern.REACT)
    .build()
)

# Use the agent
response = await agent.run("Calculate 5 + 3 and then convert 10 km to miles")
```

## Parameter Types

The decorator automatically converts Python types to JSON schema types:

| Python Type | JSON Schema Type |
|-------------|------------------|
| `str` | `string` |
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `list` | `array` |
| `dict` | `object` |
| `Optional[T]` | `T` (required: false) |
| No annotation | `string` (default) |

## Examples

### Complete Example

```python
import asyncio
from flo_ai.tool import flo_tool
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.openai_llm import OpenAI

# Define tools with decorator
@flo_tool(
    description="Perform basic calculations",
    parameter_descriptions={
        "operation": "The operation to perform (add, subtract, multiply, divide)",
        "x": "First number",
        "y": "Second number"
    }
)
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

@flo_tool()
async def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between different units."""
    # Implementation here
    return f"{value} {from_unit} = {result} {to_unit}"

async def main():
    # Create agent with tools
    llm = OpenAI(model='gpt-4-turbo-preview')
    
    agent = (
        AgentBuilder()
        .with_name("Calculator Agent")
        .with_prompt("You can perform calculations and unit conversions.")
        .with_llm(llm)
        .with_tools([calculate.tool, convert_units.tool])
        .with_reasoning(ReasoningPattern.REACT)
        .build()
    )
    
    # Test the agent
    response = await agent.run("Calculate 10 + 5 and convert 20 km to miles")
    print(response)

if __name__ == '__main__':
    asyncio.run(main())
```

## Benefits

1. **Reduced Boilerplate**: No need to manually create Tool objects with parameter definitions
2. **Type Safety**: Leverages Python's type hints for automatic parameter type detection
3. **Documentation**: Uses docstrings and parameter descriptions for better tool documentation
4. **Flexibility**: Functions can be used both as regular functions and as tools
5. **Maintainability**: Changes to function signatures automatically update the tool definition

## Migration from Manual Tool Creation

### Before (Manual)
```python
from flo_ai.tool.base_tool import Tool

async def calculate(operation: str, x: float, y: float) -> float:
    # Implementation
    pass

calculator_tool = Tool(
    name='calculate',
    description='Perform basic calculations',
    function=calculate,
    parameters={
        'operation': {
            'type': 'string',
            'description': 'The operation to perform',
        },
        'x': {'type': 'number', 'description': 'First number'},
        'y': {'type': 'number', 'description': 'Second number'},
    },
)
```

### After (With @flo_tool)
```python
from flo_ai.tool import flo_tool

@flo_tool(
    description="Perform basic calculations",
    parameter_descriptions={
        "operation": "The operation to perform",
        "x": "First number",
        "y": "Second number"
    }
)
async def calculate(operation: str, x: float, y: float) -> float:
    # Implementation
    pass

# Tool is automatically available as calculate.tool
```

The `@flo_tool` decorator significantly reduces the amount of code needed to create tools while maintaining all the functionality and flexibility of the original Tool class. 