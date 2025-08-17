# Arium YAML Configuration Guide

This guide explains how to define multi-agent workflows using YAML configuration files instead of programmatic builder patterns.

## Overview

The `AriumBuilder.from_yaml()` method allows you to define complex multi-agent workflows using declarative YAML configuration. This approach provides several benefits:

- **Declarative Configuration**: Define workflows in a human-readable format
- **Version Control**: Track workflow changes easily
- **Reusability**: Share and reuse workflow definitions
- **Separation of Concerns**: Keep workflow logic separate from implementation code
- **Clean Structure**: Focus on workflow definition without implementation details like memory

## YAML Structure

### Basic Structure

```yaml
metadata:
  name: workflow-name
  version: 1.0.0
  description: "Description of your workflow"

arium:
  agents:
    # Method 1: Reference pre-built agents (cleanest approach)
    - name: content_analyst  # Must exist in agents parameter
    - name: summarizer       # Must exist in agents parameter
    
    # Method 2: Direct configuration
    - name: validator
      role: "Quality Validator"
      job: "Validate analysis and summary quality"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        reasoning_pattern: DIRECT
      
  tools:
    - name: tool1
    - name: tool2
    
  # LLM Router definitions (NEW!)
  routers:
    - name: content_router
      type: smart  # smart, task_classifier, conversation_analysis
      routing_options:
        technical_writer: "Handle technical documentation tasks"
        creative_writer: "Handle creative writing tasks"
        editor: "Handle editing and review tasks"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        fallback_strategy: first

  workflow:
    start: content_analyst
    edges:
      - from: content_analyst
        to: [summarizer]
      - from: summarizer
        to: [validator, tool1]
        router: content_router  # References router defined above
      - from: validator
        to: [end]
      - from: tool1
        to: [end]
    end: [validator, tool1]
```

### Metadata Section

```yaml
metadata:
  name: workflow-name           # Required: Unique workflow identifier
  version: 1.0.0               # Optional: Semantic version
  description: "Description"    # Optional: Human-readable description
  tags: ["tag1", "tag2"]       # Optional: Classification tags
```

### Arium Section

#### Memory Configuration

Memory is **not configured in YAML**. Instead, pass it as a parameter to `from_yaml()`:

```python
from flo_ai.arium.memory import MessageMemory, CustomMemory

# Use default MessageMemory
builder = AriumBuilder.from_yaml(yaml_str=config)

# Or pass custom memory
custom_memory = MessageMemory()  # or your custom memory implementation
builder = AriumBuilder.from_yaml(yaml_str=config, memory=custom_memory)
```

**Why memory is handled as a parameter:**
- ✅ **Cleaner YAML**: Focuses on workflow structure, not implementation details
- ✅ **Runtime Flexibility**: Same workflow can use different memory implementations
- ✅ **Better Separation**: Memory is an execution concern, not a workflow definition concern
- ✅ **Easier Testing**: Mock different memory types without changing YAML

#### LLM Router Configuration

LLM routers can be defined directly in YAML, eliminating the need to create router functions programmatically:

```yaml
routers:
  - name: my_smart_router
    type: smart
    routing_options:
      technical_writer: "Handle technical documentation and tutorials"
      creative_writer: "Handle creative writing and storytelling"
      marketing_writer: "Handle marketing copy and sales content"
    model:
      provider: openai
      name: gpt-4o-mini
    settings:
      temperature: 0.3
      fallback_strategy: first

  - name: task_classifier
    type: task_classifier
    task_categories:
      math_solver:
        description: "Mathematical calculations and problem solving"
        keywords: ["calculate", "solve", "equation", "math"]
        examples: ["Calculate 2+2", "Solve x^2 + 5x + 6 = 0"]
      code_helper:
        description: "Programming and code assistance"
        keywords: ["code", "program", "debug", "function"]
        examples: ["Write a Python function", "Debug this code"]
    model:
      provider: openai
      name: gpt-4o-mini
    settings:
      temperature: 0.2

  - name: conversation_router
    type: conversation_analysis
    routing_logic:
      reviewer: "Route to reviewer for quality check"
      finalizer: "Route to finalizer for completion"
    model:
      provider: openai
      name: gpt-4o-mini
    settings:
      temperature: 0.1
      analysis_depth: 2
```

**Router Types:**
- **`smart`**: General-purpose routing based on content analysis
- **`task_classifier`**: Routes based on task categorization with keywords and examples
- **`conversation_analysis`**: Routes based on conversation context analysis

**Key benefits of YAML LLM routers:**
- ✅ **Declarative Configuration**: No code needed to create routers
- ✅ **Easy Modification**: Change routing logic without code changes
- ✅ **Version Control**: Track router changes in YAML files
- ✅ **Automatic Creation**: Routers are built automatically from configuration
- ✅ **Model Flexibility**: Each router can use different LLM models/settings

#### Agent Configuration

You can define agents in four ways:

**1. Reference Pre-built Agents (New):**
```yaml
agents:
  - name: content_analyst  # Must exist in agents parameter
  - name: summarizer       # Must exist in agents parameter
```

**2. Direct Configuration (Recommended):**
```yaml
agents:
  - name: my_agent
    role: Assistant  # optional
    job: "You are a helpful assistant"
    model:
      provider: openai
      name: gpt-4o-mini
      base_url: "https://api.openai.com/v1"  # optional
    settings:
      temperature: 0.7
      max_retries: 3
      reasoning_pattern: DIRECT  # DIRECT, REACT, COT
    tools: ["calculator", "web_search"]  # optional
    parser:  # optional for structured output
      name: MyParser
      fields:
        - name: result
          type: str
          description: "The result"
```

**3. Inline YAML Configuration:**
```yaml
agents:
  - name: my_agent
    yaml_config: |
      agent:
        name: my_agent
        role: Assistant
        job: "You are a helpful assistant"
        model:
          provider: openai
          name: gpt-4o-mini
        settings:
          temperature: 0.7
          max_retries: 3
          reasoning_pattern: DIRECT
```

**4. External File Reference:**
```yaml
agents:
  - name: my_agent
    yaml_file: "configs/my_agent.yaml"
```

#### Tool Configuration

```yaml
tools:
  - name: calculator
  - name: text_processor
  - name: web_search
```

**Note**: Tools must be provided as a dictionary when calling `from_yaml()` since they require actual Python functions.

#### Comparison of Agent Configuration Methods

**Reference Pre-built Agents (New):**
- ✅ Maximum reusability across workflows
- ✅ Programmatic agent building with YAML workflows
- ✅ Clean separation of agent definition and workflow
- ✅ Perfect for agent libraries
- ⚠️ Requires separate agent building step

**Direct Configuration (Recommended):**
- ✅ Clean, flat structure
- ✅ No nested YAML-in-YAML
- ✅ IDE syntax highlighting and validation
- ✅ Easier to read and maintain
- ✅ Supports all agent features directly

**Inline YAML Configuration:**
- ⚠️ Requires nested YAML string
- ⚠️ Limited IDE support for nested content
- ✅ Maintains existing workflow compatibility
- ✅ Good for complex parser configurations

**External File Reference:**
- ✅ Best for reusable agent definitions
- ✅ Supports modular architecture
- ✅ Version control friendly
- ✅ Keeps main workflow clean

#### Workflow Configuration

```yaml
workflow:
  start: agent1                    # Starting node name
  edges:
    - from: agent1                 # Source node
      to: [tool1, agent2]         # Target nodes
      router: decision_router      # Optional custom router
    - from: tool1
      to: [end]                   # 'end' is a special keyword
    - from: agent2
      to: [end]
  end: [tool1, agent2]            # End nodes
```

## Usage Examples

### Simple Linear Workflow

```python
import asyncio
from flo_ai.arium.builder import AriumBuilder

yaml_config = """
metadata:
  name: simple-workflow
  
arium:
  agents:
    - name: analyzer
      role: Content Analyst
      job: "Analyze the input content and extract key insights"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        
    - name: summarizer
      role: Summary Generator
      job: "Create a concise summary based on the analysis"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
            
  workflow:
    start: analyzer
    edges:
      - from: analyzer
        to: [summarizer]
      - from: summarizer
        to: [end]
    end: [summarizer]
"""

async def main():
    builder = AriumBuilder.from_yaml(yaml_str=yaml_config)
    result = await builder.build_and_run(["Your input text here"])
    print(result)

asyncio.run(main())
```

**Note**: To use custom memory, pass it as a parameter:
```python
from flo_ai.arium.memory import MessageMemory

custom_memory = MessageMemory()
builder = AriumBuilder.from_yaml(yaml_str=yaml_config, memory=custom_memory)
```

### Complex Workflow with Tools and Routing

```python
import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.tool.base_tool import Tool
from flo_ai.arium.memory import BaseMemory

# Custom router function
def smart_router(memory: BaseMemory) -> str:
    content = str(memory.get()[-1]).lower()
    if 'calculate' in content:
        return 'calculator'
    elif 'search' in content:
        return 'web_search'
    else:
        return 'summarizer'

# Create tools
async def calculate(x: float, y: float, op: str) -> str:
    ops = {'add': x + y, 'sub': x - y, 'mul': x * y, 'div': x / y}
    return f"Result: {ops.get(op, 'Invalid operation')}"

tools = {
    'calculator': Tool(
        name='calculator',
        description='Mathematical calculations',
        function=calculate,
        parameters={
            'x': {'type': 'number', 'description': 'First number'},
            'y': {'type': 'number', 'description': 'Second number'},
            'op': {'type': 'string', 'description': 'Operation (add, sub, mul, div)'}
        }
    )
}

routers = {'smart_router': smart_router}

yaml_config = """
metadata:
  name: complex-workflow
  
arium:
  agents:
    - name: dispatcher
      role: Request Dispatcher
      job: "Analyze input and decide next action"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        reasoning_pattern: REACT
        
    - name: summarizer
      role: Final Summarizer
      job: "Create final summary from all previous results"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
      tools: ["calculator"]  # This agent can also use tools
            
  tools:
    - name: calculator
    
  workflow:
    start: dispatcher
    edges:
      - from: dispatcher
        to: [calculator, summarizer]
        router: smart_router
      - from: calculator
        to: [summarizer]
      - from: summarizer
        to: [end]
    end: [summarizer]
"""

async def main():
    builder = AriumBuilder.from_yaml(
        yaml_str=yaml_config,
        tools=tools,
        routers=routers
    )
    
    result = await builder.build_and_run([
        "Please calculate 15 + 25 and then summarize the result"
    ])
    print(result)

asyncio.run(main())
```

### Mixed Configuration Approaches

You can also mix different configuration approaches in the same workflow:

```python
yaml_config = """
metadata:
  name: mixed-workflow
  
arium:
  agents:
    # Direct configuration
    - name: input_processor
      role: Input Processor
      job: "Process and validate input data"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        
    # Inline YAML configuration  
    - name: data_analyzer
      yaml_config: |
        agent:
          name: data_analyzer
          role: Data Analyst
          job: "Perform detailed data analysis"
          model:
            provider: anthropic
            name: claude-3-5-sonnet-20240620
          settings:
            temperature: 0.3
            reasoning_pattern: COT
            
    # External file reference
    - name: report_generator
      yaml_file: "agents/report_generator.yaml"
      
  workflow:
    start: input_processor
    edges:
      - from: input_processor
        to: [data_analyzer]
      - from: data_analyzer
        to: [report_generator]
      - from: report_generator
        to: [end]
    end: [report_generator]
"""
```

### Using Pre-built Agents

You can build agents separately using `AgentBuilder` and then reference them in your workflow YAML:

```python
import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI

# Build agents separately from YAML files
async def create_agents():
    llm = OpenAI(model="gpt-4o-mini")
    
    # Agent 1: Built from YAML file
    content_analyst_yaml = """
    agent:
      name: content_analyst
      role: Content Analyst
      job: >
        Analyze content and extract key insights, themes, and important information.
        Provide structured analysis with clear categorization.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        reasoning_pattern: COT
    """
    
    content_analyst = AgentBuilder.from_yaml(yaml_str=content_analyst_yaml).build()
    
    # Agent 2: Built programmatically
    summarizer = (AgentBuilder()
        .with_name("summarizer")
        .with_role("Summary Generator")
        .with_prompt("Create concise, actionable summaries from analysis")
        .with_llm(llm)
        .with_reasoning(ReasoningPattern.DIRECT)
        .build())
    
    # Agent 3: Built from external file
    # reporter = AgentBuilder.from_yaml(yaml_file="agents/reporter.yaml").build()
    
    return {
        'content_analyst': content_analyst,
        'summarizer': summarizer,
        # 'reporter': reporter
    }

# Clean workflow YAML that only references agents
workflow_yaml = """
metadata:
  name: content-analysis-workflow
  version: 1.0.0
  description: "Content analysis workflow using pre-built agents"

arium:
  agents:
    # Reference pre-built agents by name only
    - name: content_analyst
    - name: summarizer
    
    # You can also mix with other configuration methods
    - name: validator
      role: Content Validator
      job: "Validate the analysis and summary for accuracy"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        
  workflow:
    start: content_analyst
    edges:
      - from: content_analyst
        to: [summarizer]
      - from: summarizer
        to: [validator]
      - from: validator
        to: [end]
    end: [validator]
"""

async def main():
    # Build agents separately
    agents = await create_agents()
    
    # Create workflow with pre-built agents
    builder = AriumBuilder.from_yaml(
        yaml_str=workflow_yaml,
        agents=agents  # Pass pre-built agents
    )
    
    result = await builder.build_and_run([
        "Artificial Intelligence is revolutionizing industries across the globe. "
        "From healthcare diagnostics to financial trading, AI systems are providing "
        "unprecedented capabilities. However, challenges include ethical considerations, "
        "data privacy, and the need for human oversight in critical decisions."
    ])
    
    print(result)

asyncio.run(main())
```

## Method Signature

```python
@classmethod
def from_yaml(
    cls,
    yaml_str: Optional[str] = None,
    yaml_file: Optional[str] = None,
    memory: Optional[BaseMemory] = None,
    agents: Optional[Dict[str, Agent]] = None,
    tools: Optional[Dict[str, Tool]] = None,
    routers: Optional[Dict[str, Callable]] = None,
    base_llm: Optional[BaseLLM] = None,
) -> 'AriumBuilder':
```

### Parameters

- **yaml_str**: YAML configuration as a string
- **yaml_file**: Path to YAML configuration file
- **memory**: Memory instance to use for the workflow (defaults to MessageMemory)
- **agents**: Dictionary mapping agent names to pre-built Agent instances
- **tools**: Dictionary mapping tool names to Tool instances
- **routers**: Dictionary mapping router names to router functions
- **base_llm**: Base LLM to use for all agents if not specified individually

**Note**: Exactly one of `yaml_str` or `yaml_file` must be provided.

## Router Functions

Router functions determine the next node in the workflow based on the current memory state. They must have the following signature:

```python
def router_function(memory: BaseMemory) -> str:
    """
    Args:
        memory: Current workflow memory containing conversation history
        
    Returns:
        str: Name of the next node to execute
    """
    # Your routing logic here
    return "next_node_name"
```

### Router Return Types

Router functions must return a `Literal` type that matches the possible target nodes:

```python
from typing import Literal

def my_router(memory: BaseMemory) -> Literal["node1", "node2", "node3"]:
    # Routing logic
    if condition1:
        return "node1"
    elif condition2:
        return "node2"
    else:
        return "node3"
```

## Best Practices

### 1. Organize Agent Configurations

Keep agent configurations in separate files for better maintainability:

```
project/
├── workflows/
│   ├── main_workflow.yaml
│   └── analysis_workflow.yaml
├── agents/
│   ├── content_analyzer.yaml
│   ├── summarizer.yaml
│   └── researcher.yaml
└── tools/
    └── tool_definitions.py
```

### 2. Use Descriptive Names

Choose clear, descriptive names for agents, tools, and workflows:

```yaml
# Good
agents:
  - name: financial_analyst
  - name: risk_assessor
  - name: report_generator

# Avoid
agents:
  - name: agent1
  - name: agent2
  - name: agent3
```

### 3. Document Your Workflows

Include comprehensive metadata and comments:

```yaml
metadata:
  name: financial-analysis-workflow
  version: 2.1.0
  description: >
    Multi-stage financial analysis workflow that processes
    financial data through risk assessment and generates
    comprehensive reports with recommendations.
  tags: ["finance", "analysis", "reporting"]
  author: "Data Science Team"
  created: "2024-01-15"
  last_modified: "2024-02-01"
```

### 4. Version Your Configurations

Use semantic versioning for your workflow configurations and maintain changelog documentation.

### 5. Validate Configurations

Always test your YAML configurations thoroughly:

```python
# Test configuration loading
try:
    builder = AriumBuilder.from_yaml(yaml_file="workflow.yaml")
    print("Configuration loaded successfully")
except Exception as e:
    print(f"Configuration error: {e}")
```

## Error Handling

Common errors and their solutions:

### Missing Required Sections
```
ValueError: YAML must contain an "arium" section
```
**Solution**: Ensure your YAML has the required `arium` section.

### Agent Configuration Errors
```
ValueError: Agent {name} must have either yaml_config or yaml_file
```
**Solution**: Each agent must specify either inline `yaml_config` or `yaml_file`.

### Tool Not Found
```
ValueError: Tool {name} not found in provided tools dictionary
```
**Solution**: Ensure all referenced tools are provided in the `tools` parameter.

### Router Not Found
```
ValueError: Router {name} not found in provided routers dictionary
```
**Solution**: Ensure all referenced routers are provided in the `routers` parameter.

### Invalid Workflow Structure
```
ValueError: Workflow must specify a start node
ValueError: Workflow must specify end nodes
```
**Solution**: Ensure `workflow` section has both `start` and `end` specifications.

## Migration from Programmatic Builder

To convert existing programmatic builder code to YAML:

**Before:**
```python
builder = (AriumBuilder()
    .add_agent(agent1)
    .add_agent(agent2)
    .start_with(agent1)
    .connect(agent1, agent2)
    .end_with(agent2))
```

**After:**
```yaml
arium:
  agents:
    - name: agent1
      yaml_config: |
        # agent1 configuration
    - name: agent2
      yaml_config: |
        # agent2 configuration
        
  workflow:
    start: agent1
    edges:
      - from: agent1
        to: [agent2]
      - from: agent2
        to: [end]
    end: [agent2]
```

## Limitations

1. **Dynamic Configuration**: Router functions and tools must be provided programmatically
2. **Complex Logic**: Very complex routing logic may be better suited for programmatic definition
3. **Runtime Modification**: YAML configurations are static; runtime modifications require programmatic approach
4. **Memory Types**: Memory selection is done at runtime via parameter, not in YAML

## Future Enhancements

Planned features for future versions:

- Plugin system for router functions
- YAML-based tool definitions using function references
- Configuration validation schemas
- Hot-reloading of configurations
- Workflow debugging and visualization tools 