# Arium Builder Pattern

The `AriumBuilder` provides a fluent, easy-to-use interface for building and running Arium workflows. It eliminates the need for manual graph construction and makes it simple to create complex multi-agent workflows.

## Quick Start

```python
from flo_ai.arium import AriumBuilder, create_arium

# Simple workflow
result = await (AriumBuilder()
                .add_agent(my_agent)
                .add_tool(my_tool)
                .start_with(my_agent)
                .connect(my_agent, my_tool)
                .end_with(my_tool)
                .build_and_run(["Hello, world!"]))
```

## Key Features

- **Fluent Interface**: Chain method calls for readable workflow construction
- **Automatic Compilation**: No need to manually call `compile()`
- **Default Memory**: Uses `MessageMemory` by default if none provided
- **Easy Connections**: Simple `connect()` method for linear workflows
- **Flexible Routing**: Full support for custom router functions
- **Visualization**: Built-in graph visualization support
- **Reusable Workflows**: Build once, run multiple times

## API Reference

### AriumBuilder Methods

| Method | Description |
|--------|-------------|
| `with_memory(memory)` | Set custom memory for the workflow |
| `add_agent(agent)` | Add a single agent |
| `add_agents(agents)` | Add multiple agents |
| `add_tool(tool)` | Add a single tool |
| `add_tools(tools)` | Add multiple tools |
| `start_with(node)` | Set the starting node |
| `end_with(node)` | Add an ending node |
| `connect(from_node, to_node)` | Simple connection between nodes |
| `add_edge(from_node, to_nodes, router)` | Add edge with optional router |
| `build()` | Build the Arium instance |
| `build_and_run(inputs)` | Build and run in one step |
| `visualize(output_path, title)` | Generate workflow visualization |
| `reset()` | Reset builder to start fresh |

### Convenience Functions

- `create_arium()` - Returns a new `AriumBuilder` instance

## Usage Patterns

### 1. Linear Workflow

```python
result = await (AriumBuilder()
                .add_agent(agent1)
                .add_tool(tool1)
                .add_agent(agent2)
                .start_with(agent1)
                .connect(agent1, tool1)
                .connect(tool1, agent2)
                .end_with(agent2)
                .build_and_run(inputs))
```

### 2. Branching Workflow

```python
def my_router(memory) -> Literal["path_a", "path_b"]:
    # Your routing logic here
    return "path_a"

result = await (AriumBuilder()
                .add_agent(classifier)
                .add_tool(tool_a)
                .add_tool(tool_b)
                .add_agent(final_agent)
                .start_with(classifier)
                .add_edge(classifier, [tool_a, tool_b], my_router)
                .connect(tool_a, final_agent)
                .connect(tool_b, final_agent)
                .end_with(final_agent)
                .build_and_run(inputs))
```

### 3. Build and Reuse

```python
# Build once
arium = (AriumBuilder()
         .add_agent(my_agent)
         .start_with(my_agent)
         .end_with(my_agent)
         .build())

# Run multiple times
result1 = await arium.run(["Input 1"])
result2 = await arium.run(["Input 2"])
```

### 4. Complex Multi-Agent Workflow

```python
arium = (AriumBuilder()
         .add_agents([agent1, agent2, agent3])
         .add_tools([tool1, tool2])
         .with_memory(custom_memory)
         .start_with(agent1)
         .connect(agent1, tool1)
         .connect(tool1, agent2)
         .add_edge(agent2, [agent3, tool2], router_fn)
         .connect(tool2, agent3)
         .end_with(agent3)
         .visualize("my_workflow.png", "My Workflow")
         .build())

result = await arium.run(inputs)
```

## Migration from Manual Construction

### Before (Manual)
```python
from flo_ai.arium import Arium
from flo_ai.arium.memory import MessageMemory

# Manual construction
arium = Arium(MessageMemory())
arium.add_nodes([agent1, tool1, agent2])
arium.start_at(agent1)
arium.add_edge(agent1.name, [tool1.name])
arium.add_edge(tool1.name, [agent2.name])
arium.add_end_to(agent2)
arium.compile()

result = await arium.run(inputs)
```

### After (Builder)
```python
from flo_ai.arium import AriumBuilder

# Builder pattern
result = await (AriumBuilder()
                .add_agent(agent1)
                .add_tool(tool1)
                .add_agent(agent2)
                .start_with(agent1)
                .connect(agent1, tool1)
                .connect(tool1, agent2)
                .end_with(agent2)
                .build_and_run(inputs))
```

## Error Handling

The builder includes comprehensive validation:

- Ensures at least one agent or tool is added
- Requires a start node to be specified
- Requires at least one end node
- Validates router function signatures
- Checks for orphaned nodes

## Examples

See `examples.py` for complete working examples of different workflow patterns. 