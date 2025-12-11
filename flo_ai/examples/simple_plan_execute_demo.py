"""
Simple demonstration of PlanExecuteRouter with actual plan creation and execution.

This demo shows how the PlanExecuteRouter works with PlanAwareMemory to create,
store, and execute plans step by step, similar to how Cursor works.
"""

import asyncio
import uuid
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import PlanAwareMemory, ExecutionPlan, PlanStep, StepStatus
from flo_ai.llm import OpenAI
from flo_ai.models.agent import Agent
from flo_ai.arium.llm_router import create_plan_execute_router


async def demo_plan_aware_memory():
    """Demonstrate PlanAwareMemory functionality"""
    print('📋 DEMO: PlanAwareMemory - Plan Storage and Management')
    print('=' * 55)

    # Create plan-aware memory
    memory = PlanAwareMemory()

    # Create a sample execution plan
    plan = ExecutionPlan(
        id=str(uuid.uuid4()),
        title='Build User Authentication System',
        description='Create a complete user authentication system with login, registration, and JWT tokens',
        steps=[
            PlanStep(
                id='step_1',
                description='Design database schema for users',
                agent='developer',
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id='step_2',
                description='Implement user registration endpoint',
                agent='developer',
                dependencies=['step_1'],
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id='step_3',
                description='Implement login endpoint with JWT generation',
                agent='developer',
                dependencies=['step_1', 'step_2'],
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id='step_4',
                description='Add authentication middleware',
                agent='developer',
                dependencies=['step_3'],
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id='step_5',
                description='Write comprehensive tests',
                agent='tester',
                dependencies=['step_4'],
                status=StepStatus.PENDING,
            ),
            PlanStep(
                id='step_6',
                description='Final code review and optimization',
                agent='reviewer',
                dependencies=['step_5'],
                status=StepStatus.PENDING,
            ),
        ],
    )

    # Add plan to memory
    memory.add_plan(plan)
    print(f'✅ Plan added to memory: {plan.title}')
    print(f'📊 Total steps: {len(plan.steps)}')

    # Show plan progress
    def show_progress():
        current_plan = memory.get_current_plan()
        if current_plan:
            print(f'\n📋 Plan Progress: {current_plan.title}')
            for step in current_plan.steps:
                status_icon = {
                    StepStatus.PENDING: '○',
                    StepStatus.IN_PROGRESS: '⏳',
                    StepStatus.COMPLETED: '✅',
                    StepStatus.FAILED: '❌',
                }.get(step.status, '○')
                deps = (
                    f" (depends on: {', '.join(step.dependencies)})"
                    if step.dependencies
                    else ''
                )
                print(
                    f'  {status_icon} {step.id}: {step.description} → {step.agent}{deps}'
                )

    show_progress()

    # Simulate step execution
    print('\n🔄 Simulating step execution...')

    # Execute step 1
    current_plan = memory.get_current_plan()
    if current_plan is None:
        print('No plan available')
        return
    next_steps = current_plan.get_next_steps()
    if next_steps:
        step = next_steps[0]
        print(f'\n⏳ Executing: {step.description}')
        step.status = StepStatus.IN_PROGRESS
        memory.update_plan(current_plan)

        # Simulate completion
        step.status = StepStatus.COMPLETED
        step.result = (
            'User table created with id, email, password_hash, created_at fields'
        )
        memory.update_plan(current_plan)
        print(f'✅ Completed: {step.description}')

    # Execute step 2
    current_plan = memory.get_current_plan()
    if current_plan is None:
        print('No plan available')
        return
    next_steps = current_plan.get_next_steps()
    if next_steps:
        step = next_steps[0]
        print(f'\n⏳ Executing: {step.description}')
        step.status = StepStatus.COMPLETED
        step.result = 'POST /api/register endpoint implemented with validation'
        memory.update_plan(current_plan)
        print(f'✅ Completed: {step.description}')

    show_progress()

    # Check what's next
    current_plan = memory.get_current_plan()
    if current_plan is None:
        print('No plan available')
        return
    next_steps = current_plan.get_next_steps()
    print(f'\n🎯 Next steps ready for execution: {len(next_steps)}')
    for step in next_steps:
        print(f'  → {step.id}: {step.description} (agent: {step.agent})')

    print(f'\n📈 Plan completion: {current_plan.is_completed()}')


async def demo_programmatic_plan_execute():
    """Demonstrate programmatic usage of PlanExecuteRouter"""
    print('\n\n🏗️ DEMO: Programmatic PlanExecuteRouter Usage')
    print('=' * 55)

    # Create LLM with dummy key for demo
    llm = OpenAI(model='gpt-4o-mini', api_key='dummy-key')

    # Create agents
    Agent(
        name='planner',
        system_prompt="""You are an expert project planner. When given a task, create a detailed execution plan.

When asked to create a plan, respond with a structured format like this:

EXECUTION PLAN: [Title]
DESCRIPTION: [Brief description]

STEPS:
1. step_id: [description] → [agent_name]
2. step_id: [description] → [agent_name] (depends on: step1)
3. step_id: [description] → [agent_name] (depends on: step1, step2)

Always include clear dependencies and assign appropriate agents.""",
        llm=llm,
    )

    Agent(
        name='developer',
        system_prompt='You are a software developer. Execute development tasks step by step.',
        llm=llm,
    )

    Agent(
        name='tester',
        system_prompt='You are a QA tester. Test implementations and validate functionality.',
        llm=llm,
    )

    Agent(
        name='reviewer',
        system_prompt='You are a code reviewer. Review completed work and provide final validation.',
        llm=llm,
    )

    # Create plan-execute router
    plan_router = create_plan_execute_router(
        planner_agent='planner',
        executor_agent='developer',
        reviewer_agent='reviewer',
        additional_agents={
            'tester': 'Tests implementations and validates functionality'
        },
        llm=llm,
    )

    # Create plan-aware memory
    memory = PlanAwareMemory()

    print('✅ Created agents and PlanExecuteRouter')
    print('🎯 Router will coordinate: planner → developer → tester → reviewer')
    print('💾 Using PlanAwareMemory for plan state management')

    # Simulate routing decisions
    print('\n🧠 Simulating router decision making...')

    # Add a message to trigger planning
    memory.add({'role': 'user', 'content': 'Create a TODO app with React and Node.js'})

    # Test routing with no plan (should route to planner)
    try:
        next_agent = await plan_router(memory, None)  # type: ignore[arg-type]
        print(f'📍 Router decision (no plan): {next_agent}')
        print('   Expected: planner (to create execution plan)')

    except Exception as e:
        print(f'⚠️ Router simulation note: {e}')
        print('   (This is expected in demo mode without real LLM calls)')

    print('\n💡 In a real scenario:')
    print('  1. Router would route to planner to create execution plan')
    print('  2. Planner creates detailed plan and stores in memory')
    print('  3. Router routes to developer for first development step')
    print('  4. Developer completes step and updates plan status')
    print('  5. Router routes to next step based on plan state')
    print('  6. Process continues until all steps complete')
    print('  7. Router routes to reviewer for final validation')


async def demo_yaml_plan_execute():
    """Demonstrate YAML configuration for PlanExecuteRouter"""
    print('\n\n📄 DEMO: YAML Configuration for PlanExecuteRouter')
    print('=' * 55)

    yaml_config = """
metadata:
  name: simple-plan-execute-demo
  version: 1.0.0
  description: "Demo of plan-execute pattern"

arium:
  agents:
    - name: planner
      role: Task Planner
      job: >
        Break down complex tasks into detailed, sequential execution plans.
        Create clear steps with dependencies and agent assignments.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: executor
      role: Task Executor
      job: >
        Execute plan steps systematically, one by one.
        Report progress and update plan status.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: validator
      role: Quality Validator
      job: >
        Validate completed work and ensure quality standards.
        Provide final approval for plan completion.
      model:
        provider: openai
        name: gpt-4o-mini

  routers:
    - name: demo_plan_router
      type: plan_execute
      agents:
        planner: "Creates detailed execution plans"
        executor: "Executes plan steps systematically"
        validator: "Validates final results"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        planner_agent: planner
        executor_agent: executor
        reviewer_agent: validator

  workflow:
    start: planner
    edges:
      - from: planner
        to: [executor, validator, planner]
        router: demo_plan_router
      - from: executor
        to: [validator, executor, planner]
        router: demo_plan_router
      - from: validator
        to: [end]
    end: [validator]
"""

    try:
        # Build workflow from YAML
        builder = AriumBuilder.from_yaml(
            yaml_str=yaml_config,
            base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
        )

        builder.build()
        print('✅ YAML workflow built successfully!')
        print('📋 Configured plan-execute pattern with 3 agents')
        print('🔄 Router will coordinate planning → execution → validation')

        # Show the workflow structure
        print('\n📊 Workflow Structure:')
        print('  Start: planner')
        print('  Edges:')
        print('    planner → [executor, validator, planner] (plan_execute_router)')
        print('    executor → [validator, executor, planner] (plan_execute_router)')
        print('    validator → [end]')
        print('  End: validator')

    except Exception as e:
        print(f'ℹ️ YAML demo note: {e}')

    print('\n🎯 Key YAML Features:')
    print('  • type: plan_execute - Enables plan-execute routing')
    print('  • agents: Dict mapping agent names to descriptions')
    print('  • planner_agent: Agent responsible for creating plans')
    print('  • executor_agent: Default agent for executing steps')
    print('  • reviewer_agent: Optional agent for final review')


def show_memory_integration():
    """Show how PlanExecuteRouter integrates with memory"""
    print('\n\n💾 DEMO: Memory Integration with PlanExecuteRouter')
    print('=' * 55)

    integration_info = """
🔄 PlanExecuteRouter Memory Integration:

1. Plan Creation Phase:
   • Router detects no plan in memory
   • Routes to planner agent
   • Planner creates ExecutionPlan with steps
   • Plan stored in PlanAwareMemory

2. Execution Phase:
   • Router checks current plan state
   • Identifies next ready steps (dependencies met)
   • Routes to appropriate agent for step execution
   • Agent updates step status and results

3. Progress Tracking:
   • Plan progress visualized with status indicators:
     ○ Pending   ⏳ In Progress   ✅ Completed   ❌ Failed
   • Dependencies automatically managed
   • Failed steps trigger recovery routing

4. Memory Persistence:
   • Plan state persists across agent interactions
   • Step results and metadata stored
   • Execution context maintained

5. Completion Handling:
   • Router detects when all steps complete
   • Routes to reviewer agent (if configured)
   • Final validation and workflow completion

📊 Memory Structure:
```python
memory = PlanAwareMemory()
memory.add_plan(execution_plan)    # Store plan
current_plan = memory.get_current_plan()  # Retrieve active plan
next_steps = current_plan.get_next_steps()  # Get ready steps
```

🎯 Router Intelligence:
• Automatically routes based on plan state
• Handles step dependencies and execution order
• Provides context-aware prompts with progress
• Manages error recovery and retry logic
"""

    print(integration_info)


async def main():
    """Run all plan-execute demos"""
    print('🚀 PlanExecuteRouter Simple Demo')
    print('=' * 40)
    print('This demo shows the PlanExecuteRouter in action with actual plan')
    print('creation, storage, and step-by-step execution tracking! 🎉\n')

    # Run demos
    await demo_plan_aware_memory()
    await demo_programmatic_plan_execute()
    await demo_yaml_plan_execute()
    show_memory_integration()

    print('\n\n🎉 PlanExecuteRouter Demo Complete!')
    print('=' * 45)
    print('✅ What we demonstrated:')
    print('  • PlanAwareMemory for plan storage and state tracking')
    print('  • ExecutionPlan with steps, dependencies, and status')
    print('  • Programmatic router creation and usage')
    print('  • YAML configuration for plan-execute workflows')
    print('  • Memory integration and plan state management')

    print('\n🚀 Ready to build your own Cursor-style workflows!')
    print('  Try the PlanExecuteRouter for complex task automation! 🎯')


if __name__ == '__main__':
    asyncio.run(main())
