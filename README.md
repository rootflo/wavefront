<p align="center">
  <img src="./images/rootflo-logo.png" alt="Rootflo" width="150" />
</p>

<h1 align="center">Composable AI Agentic Workflow</h1>

<img src="https://github.blog/wp-content/uploads/2020/09/github-stars-logo_Color.png" alt="drawing" width="25"/> **Please, star the project on github (see top-right corner) if you appreciate our contribution to the community!**<img src="https://github.blog/wp-content/uploads/2020/09/github-stars-logo_Color.png" alt="drawing" width="25"/>

<p align="center">
Flo AI is a Python framework for building structured AI agents with support for multiple LLM providers, tool integration, and YAML-based configuration. Create production-ready AI agents with minimal code and maximum flexibility.
</p>

<p align="center">
  <a href="https://github.com/rootflo/flo-ai/stargazers"><img src="https://img.shields.io/github/stars/rootflo/flo-ai?style=for-the-badge" alt="GitHub stars"></a>
  <a href="https://github.com/rootflo/flo-ai/releases">
    <img src="https://img.shields.io/github/v/release/rootflo/flo-ai?display_name=release&style=for-the-badge" alt="GitHub release (latest)">
  </a>
  <a href="https://github.com/rootflo/flo-ai/graphs/commit-activity"><img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/rootflo/flo-ai/develop?style=for-the-badge">
  </a>
  <a href="https://github.com/rootflo/flo-ai/blob/develop/LICENSE"><img src="https://img.shields.io/github/license/rootflo/flo-ai?style=for-the-badge" alt="License">
  </a>
  <br/>
</p>

<p align="center">
  <br/>
  <a href="https://flo-ai.rootflo.ai" rel="" target="_blank"><strong>Checkout the docs »</strong></a>
  <br/>
  <br/>
   <a href="https://github.com/rootflo/flo-ai">Github</a>
   •
    <a href="https://rootflo.ai" target="_blank">Website</a>
   •
    <a href="https://github.com/rootflo/flo-ai/blob/develop/ROADMAP.md" target="_blank">Roadmap</a>
  </p>

  <hr />

# Flo AI 🌊

> Build production-ready AI agents with structured outputs, tool integration, and multi-LLM support

Flo AI is a Python framework that makes building production-ready AI agents and teams as easy as writing YAML. Think "Kubernetes for AI Agents" - compose complex AI architectures using pre-built components while maintaining the flexibility to create your own.

## ✨ Features

- 🔌 **Truly Composable**: Build complex AI systems by combining smaller, reusable components
- 🏗️ **Production-Ready**: Built-in best practices and optimizations for production deployments
- 📝 **YAML-First**: Define your entire agent architecture in simple YAML
- 🔧 **Flexible**: Use pre-built components or create your own
- 🤝 **Team-Oriented**: Create and manage teams of AI agents working together
- 🔄 **Langchain Compatible**: Works with all your favorite Langchain tools

## 🚀 Quick Start

### Installation

```bash
pip install flo-ai
# or using poetry
poetry add flo-ai
```

### Create Your First AI Agent in 30 seconds

```python
import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm.openai_llm import OpenAI

async def main():
    # Create a simple conversational agent
    agent = (
        AgentBuilder()
        .with_name('Math Tutor')
        .with_prompt('You are a helpful math tutor.')
        .with_llm(OpenAI(model='gpt-4o-mini'))
        .build()
    )

    response = await agent.run('What is the formula for the area of a circle?')
    print(f'Response: {response}')

asyncio.run(main())
```

### Create a Tool-Using Agent

```python
import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.tool.base_tool import Tool
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.llm.anthropic_llm import Anthropic

async def calculate(operation: str, x: float, y: float) -> float:
    if operation == 'add':
        return x + y
    elif operation == 'multiply':
        return x * y
    raise ValueError(f'Unknown operation: {operation}')

# Define a calculator tool
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

# Create a tool-using agent with Claude
agent = (
    AgentBuilder()
    .with_name('Calculator Assistant')
    .with_prompt('You are a math assistant that can perform calculations.')
    .with_llm(Anthropic(model='claude-3-5-sonnet-20240620'))
    .with_tools([calculator_tool])
    .with_reasoning(ReasoningPattern.REACT)
    .with_retries(2)
    .build()
)

response = await agent.run('Calculate 5 plus 3')
print(f'Response: {response}')
```

### Create an Agent with Structured Output

```python
import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm.openai_llm import OpenAI

# Define output schema for structured responses
math_schema = {
    'type': 'object',
    'properties': {
        'solution': {'type': 'string', 'description': 'The step-by-step solution'},
        'answer': {'type': 'string', 'description': 'The final answer'},
    },
    'required': ['solution', 'answer'],
}

# Create an agent with structured output
agent = (
    AgentBuilder()
    .with_name('Structured Math Solver')
    .with_prompt('You are a math problem solver that provides structured solutions.')
    .with_llm(OpenAI(model='gpt-4o'))
    .with_output_schema(math_schema)
    .build()
)

response = await agent.run('Solve: 2x + 5 = 15')
print(f'Structured Response: {response}')
```

## 📝 YAML Configuration

Define your agents using YAML for easy configuration and deployment:

```yaml
apiVersion: flo/alpha-v1
kind: FloAgent
metadata:
  name: email-summary-flo
  version: 1.0.0
  description: "Agent for analyzing email threads"
agent:
  name: EmailSummaryAgent
  kind: llm
  role: Email communication expert
  model:
    provider: openai
    name: gpt-4o-mini
  settings:
    temperature: 0
    max_retries: 3
    reasoning_pattern: DIRECT
  job: >
    You are given an email thread between a customer and a support agent.
    Your job is to analyze the behavior, sentiment, and communication style.
  parser:
    name: EmailSummary
    fields:
      - name: sender_type
        type: literal
        description: "Who sent the latest email"
        values:
          - value: customer
            description: "Latest email was sent by customer"
          - value: agent
            description: "Latest email was sent by support agent"
      - name: summary
        type: str
        description: "A comprehensive summary of the email"
      - name: resolution_status
        type: literal
        description: "Issue resolution status"
        values:
          - value: resolved
            description: "Issue appears resolved"
          - value: unresolved
            description: "Issue requires attention"
```

```python
from flo_ai.builder.agent_builder import AgentBuilder

# Create agent from YAML
builder = AgentBuilder.from_yaml(yaml_str=yaml_config)
agent = builder.build()

# Use the agent
result = await agent.run(email_thread)
```

## 🛠️ Tools

Create custom tools easily with async support:

```python
from flo_ai.tool.base_tool import Tool

async def weather_lookup(city: str) -> str:
    # Your weather API call here
    return f"Weather in {city}: Sunny, 25°C"

weather_tool = Tool(
    name='weather_lookup',
    description='Get current weather for a city',
    function=weather_lookup,
    parameters={
        'city': {
            'type': 'string',
            'description': 'City name to get weather for'
        }
    }
)

# Add to your agent
agent = (
    AgentBuilder()
    .with_name('Weather Assistant')
    .with_llm(OpenAI(model='gpt-4o-mini'))
    .with_tools([weather_tool])
    .build()
)
```

### 🎯 @flo_tool Decorator

The `@flo_tool` decorator automatically converts any Python function into a `Tool` object with minimal boilerplate:

```python
from flo_ai.tool import flo_tool

@flo_tool(
    description="Perform mathematical calculations",
    parameter_descriptions={
        "operation": "The operation to perform (add, subtract, multiply, divide)",
        "x": "First number",
        "y": "Second number"
    }
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

# Function can be called normally
result = await calculate("add", 5, 3)  # Returns 8

# Tool object is automatically available
agent = (
    AgentBuilder()
    .with_name('Calculator Agent')
    .with_llm(OpenAI(model='gpt-4o-mini'))
    .with_tools([calculate.tool])  # Access the tool via .tool attribute
    .build()
)
```

**Key Benefits:**
- ✅ **Automatic parameter extraction** from type hints
- ✅ **Flexible descriptions** via docstrings or custom descriptions
- ✅ **Type conversion** from Python types to JSON schema
- ✅ **Dual functionality** - functions work normally AND as tools
- ✅ **Async support** for both sync and async functions

**Simple Usage:**
```python
@flo_tool()
async def convert_units(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between different units (km/miles, kg/lbs, celsius/fahrenheit)."""
    # Implementation here
    return f"{value} {from_unit} = {result} {to_unit}"

# Tool is automatically available as convert_units.tool
```

**With Custom Metadata:**
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
    return f"Weather in {city}: sunny"
```

> 📖 **For detailed documentation on the `@flo_tool` decorator, see [README_flo_tool.md](flo_ai/README_flo_tool.md)**

## 🧠 Reasoning Patterns

Flo AI supports multiple reasoning patterns:

- **DIRECT**: Simple question-answer without step-by-step reasoning
- **COT (Chain of Thought)**: Step-by-step reasoning before providing the answer
- **REACT**: Reasoning and action cycles for tool-using agents

```python
from flo_ai.models.base_agent import ReasoningPattern

agent = (
    AgentBuilder()
    .with_name('Reasoning Agent')
    .with_llm(OpenAI(model='gpt-4o'))
    .with_reasoning(ReasoningPattern.COT)  # or REACT, DIRECT
    .build()
)
```

## 🔧 LLM Providers

### OpenAI
```python
from flo_ai.llm.openai_llm import OpenAI

llm = OpenAI(
    model='gpt-4o',
    temperature=0.7,
    api_key='your-api-key'  # or set OPENAI_API_KEY env var
)
```

### Anthropic Claude
```python
from flo_ai.llm.anthropic_llm import Anthropic

llm = Anthropic(
    model='claude-3-5-sonnet-20240620',
    temperature=0.7,
    api_key='your-api-key'  # or set ANTHROPIC_API_KEY env var
)
```

### Ollama (Local)
```python
from flo_ai.llm.ollama_llm import Ollama

llm = Ollama(
    model='llama2',
    base_url='http://localhost:11434'
)
```

## 📊 Output Formatting

Use Pydantic models or JSON schemas for structured outputs:

```python
from pydantic import BaseModel, Field

class MathSolution(BaseModel):
    solution: str = Field(description="Step-by-step solution")
    answer: str = Field(description="Final answer")
    confidence: float = Field(description="Confidence level (0-1)")

agent = (
    AgentBuilder()
    .with_name('Math Solver')
    .with_llm(OpenAI(model='gpt-4o'))
    .with_output_schema(MathSolution)
    .build()
)
```

## 🔄 Error Handling

Built-in retry mechanisms and error recovery:

```python
agent = (
    AgentBuilder()
    .with_name('Robust Agent')
    .with_llm(OpenAI(model='gpt-4o'))
    .with_retries(3)  # Retry up to 3 times on failure
    .build()
)
```

## 📚 Examples

Check out the `examples/` directory for comprehensive examples:

- `agent_builder_usage.py` - Basic agent creation patterns
- `yaml_agent_example.py` - YAML-based agent configuration
- `output_formatter.py` - Structured output examples
- `multi_tool_example.py` - Multi-tool agent examples
- `cot_agent_example.py` - Chain of Thought reasoning
- `usage.py` and `usage_claude.py` - Provider-specific examples

## 🚀 Advanced Features

### Custom Tool Creation
```python
from flo_ai.tool.base_tool import Tool

async def custom_function(param1: str, param2: int) -> dict:
    # Your async logic here
    return {"result": f"Processed {param1} with {param2}"}

custom_tool = Tool(
    name='custom_function',
    description='A custom async tool',
    function=custom_function,
    parameters={
        'param1': {'type': 'string', 'description': 'First parameter'},
        'param2': {'type': 'integer', 'description': 'Second parameter'}
    }
)
```

### YAML Parser Integration
```python
from flo_ai.formatter.yaml_format_parser import FloYamlParser

# Create parser from YAML definition
parser = FloYamlParser.create(yaml_dict=yaml_config)
output_schema = parser.get_format()

agent = (
    AgentBuilder()
    .with_name('YAML Configured Agent')
    .with_llm(OpenAI(model='gpt-4o'))
    .with_output_schema(output_schema)
    .build()
)
```

## 📖 Documentation

Visit our [comprehensive documentation](https://flo-ai.rootflo.ai) for:
- Detailed tutorials
- API reference
- Best practices
- Advanced examples
- Architecture deep-dives

**Additional Resources:**
- [@flo_tool Decorator Guide](flo_ai/README_flo_tool.md) - Complete guide to the `@flo_tool` decorator
- [Examples Directory](examples/) - Ready-to-run code examples
- [Contributing Guide](CONTRIBUTING.md) - How to contribute to Flo AI

## 🌟 Why Flo AI?

### For Developers
- **Simple Setup**: Get started in minutes with minimal configuration
- **Flexible**: Use YAML or code-based configuration
- **Production Ready**: Built-in error handling and retry mechanisms
- **Multi-LLM**: Switch between providers easily

### For Teams
- **Maintainable**: YAML-first approach makes configurations versionable
- **Testable**: Each component can be tested independently
- **Scalable**: From simple agents to complex multi-tool systems

## 🎯 Use Cases

- 🤖 Customer Service Automation
- 📊 Data Analysis and Processing
- 📝 Content Generation and Summarization
- 🔍 Research and Information Retrieval
- 🎯 Task-Specific AI Assistants
- 📧 Email Analysis and Classification

## 🤝 Contributing

We love your input! Check out our [Contributing Guide](CONTRIBUTING.md) to get started. Ways to contribute:

- 🐛 Report bugs
- 💡 Propose new features
- 📝 Improve documentation
- 🔧 Submit PRs

## 📜 License

Flo AI is [MIT Licensed](LICENSE).

## 🙏 Acknowledgments

Built with ❤️ using:
- [LangChain](https://github.com/hwchase17/langchain)
- [Pydantic](https://github.com/pydantic/pydantic)
- [OpenAI](https://openai.com/)
- [Anthropic](https://www.anthropic.com/)

---

<div align="center">
  <strong>Built with ❤️ by the <a href="http://rootflo.ai">rootflo</a> team</strong>
  <br><a href="https://github.com/rootflo/flo-ai/discussions">Community</a> •
  <a href="https://flo-ai.rootflo.ai">Documentation</a>
</div>
