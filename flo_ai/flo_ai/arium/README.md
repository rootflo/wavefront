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
- **🧠 LLM-Powered Routing**: Intelligent routing using Large Language Models
- **📊 Event Monitoring**: Real-time workflow execution monitoring with customizable callbacks
- **Visualization**: Built-in graph visualization support
- **Reusable Workflows**: Build once, run multiple times

## 📊 Event Monitoring

Arium provides comprehensive event monitoring capabilities that allow you to track workflow execution in real-time. This is invaluable for debugging, performance monitoring, and understanding how your workflows behave.

### Key Features

- **Real-time Events**: Monitor workflow lifecycle, node execution, and routing decisions
- **Custom Callbacks**: Write your own event handlers for logging, metrics, or debugging
- **Event Filtering**: Choose which types of events to monitor
- **Zero Configuration**: Works out of the box with sensible defaults
- **Performance Tracking**: Automatic execution time measurement for nodes

### Available Event Types

| Event Type | Description |
|------------|-------------|
| `WORKFLOW_STARTED` | Fired when workflow execution begins |
| `WORKFLOW_COMPLETED` | Fired when workflow completes successfully |
| `WORKFLOW_FAILED` | Fired when workflow fails with an error |
| `NODE_STARTED` | Fired when a node (agent/tool) begins execution |
| `NODE_COMPLETED` | Fired when a node completes successfully |
| `NODE_FAILED` | Fired when a node fails with an error |
| `ROUTER_DECISION` | Fired when a router chooses the next node |
| `EDGE_TRAVERSED` | Fired when moving from one node to another |

### Basic Usage

```python
from flo_ai.arium import AriumBuilder, AriumEventType, default_event_callback

# Enable event monitoring with default callback (logs to console)
arium = (AriumBuilder()
         .add_agent(my_agent)
         .add_tool(my_tool)
         .start_with(my_agent)
         .connect(my_agent, my_tool)
         .end_with(my_tool)
         .build())

result = await arium.run(
    inputs=["Process this"],
    event_callback=default_event_callback
)
```

### Custom Event Callbacks

```python
def my_event_handler(event):
    """Custom event handler for specialized logging"""
    print(f"🔔 {event.event_type.value}: {event.node_name}")
    if event.execution_time:
        print(f"   ⏱️ Took {event.execution_time:.2f}s")
    if event.error:
        print(f"   ❌ Error: {event.error}")

# Use your custom callback
arium = (AriumBuilder()
         .add_agent(my_agent)
         .start_with(my_agent)
         .end_with(my_agent)
         .build())

result = await arium.run(
    inputs=["Hello world"],
    event_callback=my_event_handler
)
```

### Event Filtering

Monitor only specific types of events by providing an `events_filter`:

```python
from flo_ai.arium import AriumEventType, default_event_callback

# Only monitor workflow lifecycle and node completions
important_events = [
    AriumEventType.WORKFLOW_STARTED,
    AriumEventType.NODE_COMPLETED,
    AriumEventType.WORKFLOW_COMPLETED,
    AriumEventType.WORKFLOW_FAILED
]

arium = (AriumBuilder()
         .add_agent(my_agent)
         .start_with(my_agent)
         .end_with(my_agent)
         .build())

result = await arium.run(
    inputs=["Process this"],
    event_callback=default_event_callback,
    events_filter=important_events
)
```

### Silent Execution

By default, workflows run silently. You can use either approach:

```python
# Option 1: Use build_and_run() for convenience (no events)
result = await (AriumBuilder()
                .add_agent(my_agent)
                .start_with(my_agent)
                .end_with(my_agent)
                .build_and_run(["Silent execution"]))

# Option 2: Use build() then run() (no events)
arium = (AriumBuilder()
         .add_agent(my_agent)
         .start_with(my_agent)
         .end_with(my_agent)
         .build())

result = await arium.run(["Silent execution"])
```

### Event Monitoring vs Build-and-Run

**Important**: Event monitoring is only available through the `Arium.run()` method. The AriumBuilder's `build_and_run()` convenience method does not support event parameters.

- **For event monitoring**: Use `.build()` then `arium.run(inputs, event_callback=...)`
- **For simple execution**: Use `.build_and_run(inputs)` for convenience
- **For reusable workflows**: Use `.build()` once, then call `arium.run()` multiple times

### Event Data Structure

Each event is an `AriumEvent` object with the following properties:

```python
@dataclass
class AriumEvent:
    event_type: AriumEventType          # Type of event
    timestamp: float                    # Unix timestamp
    node_name: Optional[str] = None     # Name of involved node
    node_type: Optional[str] = None     # Type: 'agent', 'tool', 'start', 'end'
    execution_time: Optional[float] = None  # Node execution time in seconds
    error: Optional[str] = None         # Error message if applicable
    router_choice: Optional[str] = None # Node chosen by router
    metadata: Optional[dict] = None     # Additional event data
```

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
| `build_and_run(inputs, variables=None)` | Build and run in one step (no event monitoring support) |
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

# Run multiple times (with optional event monitoring)
result1 = await arium.run(["Input 1"], event_callback=default_event_callback)
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

## 🧠 LLM-Powered Routing

Arium now supports intelligent routing using Large Language Models! Instead of writing complex routing logic, let an LLM analyze the conversation and decide which agent should handle the next step.

### Quick Example

```python
from flo_ai.arium import create_llm_router

# Create an intelligent router
smart_router = create_llm_router(
    "smart",
    routing_options={
        "researcher": "Gather information and conduct research",
        "analyst": "Analyze data and provide insights",
        "writer": "Create summaries and reports"
    }
)

# Use in your workflow
result = await (AriumBuilder()
                .add_agents([researcher, analyst, writer])
                .start_with(researcher)
                .add_edge(researcher, [analyst, writer], smart_router)
                .end_with(writer)
                .build_and_run(["Research AI trends and create a report"]))
```

### Router Types

- **SmartRouter**: General-purpose intelligent routing
- **TaskClassifierRouter**: Classify tasks and route to specialists
- **ConversationAnalysisRouter**: Analyze conversation flow for routing

**📖 For detailed LLM routing documentation, see [README_LLM_Router.md](README_LLM_Router.md)**

## Examples

See `examples.py` for complete working examples of different workflow patterns.
See `examples/llm_router_example.py` for comprehensive LLM routing examples. 