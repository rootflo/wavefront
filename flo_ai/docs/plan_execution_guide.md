# Plan Execution Framework Guide

The Flo AI framework provides built-in support for plan-and-execute workflows, making it easy to create multi-step, coordinated agent workflows.

## Quick Start

### 1. Basic Software Development Workflow

```python
import asyncio
from flo_ai.llm import OpenAI
from flo_ai.arium.memory import PlanAwareMemory
from flo_ai.arium.llm_router import create_plan_execute_router
from flo_ai.arium import AriumBuilder
from flo_ai.models.plan_agents import create_software_development_agents

async def main():
    # Setup (3 lines!)
    llm = OpenAI(model='gpt-4o', api_key='your-key')
    memory = PlanAwareMemory()
    agents = create_software_development_agents(memory, llm)
    
    # Create router
    router = create_plan_execute_router(
        planner_agent='planner',
        executor_agent='developer',
        reviewer_agent='reviewer',
        additional_agents={'tester': 'Tests implementations'},
        llm=llm,
    )
    
    # Build workflow
    agent_list = list(agents.values())
    arium = (
        AriumBuilder()
        .with_memory(memory)
        .add_agents(agent_list)
        .start_with(agents['planner'])
        .add_edge(agents['planner'], agent_list, router)
        .add_edge(agents['developer'], agent_list, router)
        .add_edge(agents['tester'], agent_list, router)
        .add_edge(agents['reviewer'], agent_list, router)
        .end_with(agents['reviewer'])
        .build()
    )
    
    # Execute
    result = await arium.run(['Create a user authentication API'])

asyncio.run(main())
```

### 2. Custom Plan Workflow

```python
from flo_ai.models.plan_agents import PlannerAgent, ExecutorAgent

# Create custom agents
planner = PlannerAgent(memory, llm, name='planner')
researcher = ExecutorAgent(memory, llm, name='researcher')
analyst = ExecutorAgent(memory, llm, name='analyst')
writer = ExecutorAgent(memory, llm, name='writer')

# Use the same pattern as above with your custom agents
```

## Key Components

### Plan Agents

- **`PlannerAgent`**: Creates execution plans automatically
- **`ExecutorAgent`**: Executes plan steps and tracks progress
- **`create_software_development_agents()`**: Pre-configured dev team

### Plan Tools

- **`PlanTool`**: Parses and stores execution plans (from `flo_ai.tool.plan_tool`)
- **`StepTool`**: Marks steps as completed (from `flo_ai.tool.plan_tool`)
- **`PlanStatusTool`**: Checks plan progress (from `flo_ai.tool.plan_tool`)

### Memory

- **`PlanAwareMemory`**: Stores both conversations and execution plans

### Router

- **`create_plan_execute_router()`**: Intelligent routing for plan workflows

## How It Works

1. **Planning Phase**: Router sends task to planner agent
2. **Plan Storage**: Planner creates and stores ExecutionPlan in memory
3. **Execution Phase**: Router routes to appropriate agents based on plan steps
4. **Progress Tracking**: Agents mark steps as completed using tools
5. **Completion**: Router detects when all steps are done

## Plan Format

Plans are created in this standard format:

```
EXECUTION PLAN: [Title]
DESCRIPTION: [Description]

STEPS:
1. step_1: [Task description] → agent_name
2. step_2: [Task description] → agent_name (depends on: step_1)
3. step_3: [Task description] → agent_name (depends on: step_1, step_2)
```

## Benefits

- **Minimal Code**: Pre-built components handle all the complexity
- **Automatic Plan Management**: Plans are created, stored, and tracked automatically
- **Flexible**: Create custom agents for any domain
- **Robust**: Built-in error handling and progress tracking
- **Reusable**: Tools and agents work across different workflows

## Examples

See the `examples/` directory for:
- `fixed_plan_execute_demo.py` - Basic software development workflow
- `custom_plan_execute_demo.py` - Custom research workflow
