# LLM-Powered Routing for Arium Workflows

This document describes the LLM-powered routing functionality that enables intelligent, context-aware routing decisions in Arium workflows.

## Overview

Traditional routers require pre-written logic to determine the next agent in a workflow. LLM-powered routers use Large Language Models to analyze conversation context and make intelligent routing decisions dynamically.

## Key Benefits

- 🧠 **Intelligent Decision Making**: Uses LLMs to understand context and intent
- 🔄 **Dynamic Routing**: No need to pre-program all routing scenarios
- 📊 **Context Awareness**: Considers full conversation history when routing
- 🛠️ **Easy Integration**: Drop-in replacement for traditional routers
- 🎯 **Specialized Patterns**: Pre-built routers for common workflows

## Router Types

### 1. SmartRouter
General-purpose router that analyzes tasks and routes to appropriate agents.

```python
from flo_ai.arium import create_llm_router

# Create a smart router
router = create_llm_router(
    "smart",
    routing_options={
        "researcher": "Gather information and conduct research",
        "analyst": "Analyze data and perform calculations", 
        "writer": "Create reports and summaries"
    },
    context_description="a research workflow"
)
```

### 2. TaskClassifierRouter
Specialized router that classifies tasks based on keywords and examples.

```python
router = create_llm_router(
    "task_classifier",
    task_categories={
        "math_specialist": {
            "description": "Handle mathematical calculations and analysis",
            "keywords": ["calculate", "math", "statistics", "compute"],
            "examples": ["Calculate the average", "What's the growth rate?"]
        },
        "text_specialist": {
            "description": "Handle text analysis and writing tasks",
            "keywords": ["write", "analyze", "grammar", "content"],
            "examples": ["Write a summary", "Analyze sentiment"]
        }
    }
)
```

### 3. ConversationAnalysisRouter
Router that analyzes conversation flow and determines next steps.

```python
router = create_llm_router(
    "conversation_analysis",
    routing_logic={
        "planner": "Route here when planning is needed",
        "executor": "Route here when work needs to be executed", 
        "reviewer": "Route here when work needs review"
    },
    analysis_depth=3  # Analyze last 3 messages
)
```

## Usage Patterns

### Factory Function Pattern

The simplest way to create LLM routers:

```python
from flo_ai.arium import create_llm_router, AriumBuilder

# Create router
intelligent_router = create_llm_router(
    "smart",
    routing_options={
        "agent1": "Description of agent1's role",
        "agent2": "Description of agent2's role"
    }
)

# Use in workflow
result = await (
    AriumBuilder()
    .add_agents([agent1, agent2])
    .start_with(agent1)
    .add_edge(agent1, [agent1, agent2], intelligent_router)
    .end_with(agent2)
    .build_and_run(inputs)
)
```

### Decorator Pattern

For clean, declarative router definitions:

```python
from flo_ai.arium import llm_router
from typing import Literal

@llm_router({
    "researcher": "Conduct research and gather information",
    "analyst": "Analyze data and provide insights"
})
def my_router(memory: BaseMemory) -> Literal["researcher", "analyst"]:
    """Smart router for research workflow"""
    pass  # Implementation provided by decorator
```

### YAML Integration

LLM routers work seamlessly with YAML workflows:

```yaml
arium:
  workflow:
    start: classifier
    edges:
      - from: classifier
        to: [researcher, analyst, writer]
        router: intelligent_router  # LLM router provided in Python
```

```python
# Provide router to YAML workflow
result = await (
    AriumBuilder()
    .from_yaml(
        yaml_str=workflow_yaml,
        routers={"intelligent_router": my_llm_router}
    )
    .build_and_run(inputs)
)
```

## Configuration Options

### LLM Configuration

```python
from flo_ai.llm import OpenAI

# Configure LLM for routing
llm = OpenAI(model="gpt-4o", temperature=0.1)

router = create_llm_router(
    "smart",
    routing_options=options,
    llm=llm,  # Custom LLM
    temperature=0.1,  # Lower temperature for more deterministic routing
    max_retries=3,  # Retry failed LLM calls
    fallback_strategy="first"  # Fallback when LLM fails
)
```

### Fallback Strategies

When LLM routing fails, these strategies are available:

- `"first"`: Route to first option (default)
- `"last"`: Route to last option  
- `"random"`: Route to random option

## Best Practices

### 1. Clear Option Descriptions

Provide clear, specific descriptions for routing options:

```python
# Good
routing_options = {
    "data_analyst": "Analyze numerical data, create charts, and calculate statistics",
    "text_analyst": "Analyze text content, extract insights, and summarize information"
}

# Avoid
routing_options = {
    "analyst1": "Handles analysis",
    "analyst2": "Does other analysis"
}
```

### 2. Context Descriptions

Add context to help the LLM understand the workflow:

```python
router = create_llm_router(
    "smart",
    routing_options=options,
    context_description="a financial analysis workflow for investment decisions"
)
```

### 3. Task Categories with Examples

For TaskClassifierRouter, include relevant keywords and examples:

```python
task_categories = {
    "researcher": {
        "description": "Information gathering and research tasks",
        "keywords": ["research", "find", "investigate", "gather", "search"],
        "examples": [
            "Find information about market trends",
            "Research competitor analysis",
            "Gather data on customer preferences"
        ]
    }
}
```

### 4. Error Handling

Configure appropriate retry and fallback behavior:

```python
router = create_llm_router(
    "smart",
    routing_options=options,
    max_retries=3,  # Retry failed calls
    fallback_strategy="first",  # Clear fallback
    temperature=0.1  # Deterministic responses
)
```

## Advanced Usage

### Custom Router Classes

Create custom routers by extending `BaseLLMRouter`:

```python
from flo_ai.arium.llm_router import BaseLLMRouter

class CustomRouter(BaseLLMRouter):
    def get_routing_options(self) -> Dict[str, str]:
        return {"agent1": "Description", "agent2": "Description"}
    
    def get_routing_prompt(self, memory, options) -> str:
        # Custom prompt logic
        return "Your custom routing prompt"

# Use custom router
router_instance = CustomRouter()
def custom_router_function(memory):
    return asyncio.run(router_instance.route(memory))
```

### Multi-Stage Routing

Combine multiple routers for complex workflows:

```python
# First stage: Task classification
task_router = create_llm_router("task_classifier", ...)

# Second stage: Specialist routing
specialist_router = create_llm_router("smart", ...)

# Use in multi-stage workflow
workflow = (
    AriumBuilder()
    .add_agent(classifier)
    .add_edge(classifier, [research_specialist, analysis_specialist], task_router)
    .add_edge(research_specialist, [writer, reviewer], specialist_router)
    # ... more stages
)
```

## Troubleshooting

### Common Issues

1. **Router Returns Invalid Option**
   - Check that routing options match return type annotations
   - Ensure LLM has clear instructions
   - Verify option descriptions are distinct

2. **LLM Calls Failing**
   - Check API key configuration
   - Verify network connectivity
   - Consider increasing `max_retries`

3. **Inconsistent Routing**
   - Lower `temperature` for more deterministic results
   - Provide more specific option descriptions
   - Add examples to task categories

### Debugging

Enable debug logging to see routing decisions:

```python
import logging
logging.getLogger('flo_ai').setLevel(logging.DEBUG)

# Router decisions will be logged
router = create_llm_router(...)
```

## Examples

See `examples/llm_router_example.py` for comprehensive usage examples demonstrating:

- Smart router with factory functions
- Decorator-based router definitions  
- Task classifier for specialized routing
- Convenience functions for common patterns
- Conversation analysis for flow-based routing

## API Reference

### Functions

- `create_llm_router(router_type, **config)`: Factory function for creating LLM routers
- `llm_router(routing_options, **kwargs)`: Decorator for creating routers

### Classes

- `BaseLLMRouter`: Abstract base class for LLM routers
- `SmartRouter`: General-purpose intelligent router
- `TaskClassifierRouter`: Task classification-based router
- `ConversationAnalysisRouter`: Conversation flow analysis router

For detailed API documentation, see the docstrings in `flo_ai/arium/llm_router.py`.
