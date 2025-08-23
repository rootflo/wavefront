"""
Live PlanExecuteRouter Demo - Real OpenAI LLM Integration

A focused demo showing PlanExecuteRouter with actual LLM calls.
Set OPENAI_API_KEY environment variable to run.

This demonstrates:
1. Automatic task breakdown into execution plans
2. Step-by-step execution with progress tracking
3. Intelligent routing between planning and execution phases
"""

import asyncio
import os
from flo_ai.models.agent import Agent
from flo_ai.llm import OpenAI
from flo_ai.arium.memory import PlanAwareMemory, ExecutionPlan, PlanStep, StepStatus
from flo_ai.arium.llm_router import create_plan_execute_router
from flo_ai.arium import AriumBuilder


class PlanParser:
    """Helper to parse LLM-generated plans into ExecutionPlan objects"""

    @staticmethod
    def parse_plan_from_text(
        plan_text: str, planner_agent: str = 'planner'
    ) -> ExecutionPlan:
        """Parse structured plan text into ExecutionPlan object"""
        import uuid
        import re

        # Extract title and description
        title_match = re.search(r'EXECUTION PLAN:\s*(.+)', plan_text)
        title = title_match.group(1).strip() if title_match else 'Generated Plan'

        desc_match = re.search(r'DESCRIPTION:\s*(.+)', plan_text)
        description = desc_match.group(1).strip() if desc_match else 'Execution plan'

        # Extract steps
        steps = []
        step_pattern = (
            r'(\d+)\.\s*(\w+):\s*(.+?)\s*→\s*(\w+)(?:\s*\(depends on:\s*([^)]+)\))?'
        )

        for match in re.finditer(step_pattern, plan_text):
            step_num, step_id, step_desc, agent, deps_str = match.groups()

            dependencies = []
            if deps_str:
                dependencies = [dep.strip() for dep in deps_str.split(',')]

            step = PlanStep(
                id=step_id,
                description=step_desc.strip(),
                agent=agent,
                dependencies=dependencies,
                status=StepStatus.PENDING,
            )
            steps.append(step)

        return ExecutionPlan(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            steps=steps,
            created_by=planner_agent,
        )


async def run_live_demo():
    """Run a live demo with real OpenAI API calls"""
    print('🚀 Live PlanExecuteRouter Demo')
    print('=' * 40)

    # Check API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY environment variable not set')
        print('   Set it with: export OPENAI_API_KEY=your_key_here')
        return

    print('✅ OpenAI API key found')

    # Create LLM
    llm = OpenAI(model='gpt-4o-mini', api_key=api_key)

    # Create agents with specific roles
    planner = Agent(
        name='planner',
        system_prompt="""You are a project planner. Create execution plans in this exact format:

EXECUTION PLAN: [Title]
DESCRIPTION: [Brief description]

STEPS:
1. step_1: [Description] → [agent]
2. step_2: [Description] → [agent] (depends on: step_1)
3. step_3: [Description] → [agent] (depends on: step_1, step_2)

Use agents: developer, tester, reviewer
Keep steps clear and actionable.""",
        llm=llm,
    )

    developer = Agent(
        name='developer',
        system_prompt="""You are a developer executing specific implementation steps.
Acknowledge the step you're working on and provide detailed implementation.""",
        llm=llm,
    )

    tester = Agent(
        name='tester',
        system_prompt="""You are a tester validating implementations.
Create test scenarios and report validation results.""",
        llm=llm,
    )

    reviewer = Agent(
        name='reviewer',
        system_prompt="""You are a reviewer providing final validation.
Review completed work and give final approval.""",
        llm=llm,
    )

    print('✅ Created agents: planner, developer, tester, reviewer')

    # Create memory and router
    memory = PlanAwareMemory()

    plan_router = create_plan_execute_router(
        planner_agent='planner',
        executor_agent='developer',
        reviewer_agent='reviewer',
        additional_agents={'tester': 'Tests implementations'},
        llm=llm,
    )

    print('✅ Created PlanExecuteRouter with PlanAwareMemory')

    # Create workflow
    arium = (
        AriumBuilder()
        .with_memory(memory)
        .add_agents([planner, developer, tester, reviewer])
        .start_with(planner)
        .add_edge(planner, [developer, tester, reviewer, planner], plan_router)
        .add_edge(developer, [tester, reviewer, developer, planner], plan_router)
        .add_edge(tester, [developer, reviewer, tester, planner], plan_router)
        .add_edge(reviewer, [developer, tester, reviewer, planner], plan_router)
        .end_with(reviewer)
        .build()
    )

    print('✅ Built Arium workflow')

    # Task to execute
    task = 'Create a simple user registration API with email validation'

    print(f'\n📋 Task: {task}')
    print('\n🔄 Executing plan-and-execute workflow...')
    print(
        '   Watch as the router coordinates planning → development → testing → review'
    )

    try:
        # Execute workflow
        result = await arium.run([task])

        print('\n' + '=' * 50)
        print('🎉 WORKFLOW COMPLETED!')
        print('=' * 50)

        # Show results
        if result:
            final_result = result[-1] if isinstance(result, list) else result
            print('\n📄 Final Output:')
            print('-' * 30)
            print(final_result)

        # Show execution plan if created
        current_plan = memory.get_current_plan()
        if current_plan:
            print(f'\n📊 Execution Plan: {current_plan.title}')
            print(f'Description: {current_plan.description}')
            print(f'Steps: {len(current_plan.steps)}')
            print(f'Completed: {current_plan.is_completed()}')

            print('\n📋 Step Progress:')
            for step in current_plan.steps:
                status_icon = {
                    StepStatus.PENDING: '○',
                    StepStatus.IN_PROGRESS: '⏳',
                    StepStatus.COMPLETED: '✅',
                    StepStatus.FAILED: '❌',
                }.get(step.status, '○')
                deps = (
                    f" (deps: {', '.join(step.dependencies)})"
                    if step.dependencies
                    else ''
                )
                print(
                    f'  {status_icon} {step.id}: {step.description} → {step.agent}{deps}'
                )

        print('\n💡 What happened:')
        print('  • Router started by routing to planner')
        print('  • Planner created detailed execution plan')
        print('  • Router routed to developer for implementation steps')
        print('  • Router routed to tester for validation')
        print('  • Router routed to reviewer for final approval')
        print('  • Plan state tracked in PlanAwareMemory throughout')

    except Exception as e:
        print(f'\n❌ Error: {e}')
        print('This could be due to API rate limits or network issues.')


async def run_simple_plan_creation():
    """Demo just the plan creation part"""
    print('\n\n📋 Plan Creation Demo')
    print('=' * 30)

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY not set')
        return

    llm = OpenAI(model='gpt-4o-mini', api_key=api_key)

    planner = Agent(
        name='planner',
        system_prompt="""Create an execution plan in this format:

EXECUTION PLAN: [Title]
DESCRIPTION: [Description]

STEPS:
1. step_1: [Task description] → developer
2. step_2: [Task description] → developer (depends on: step_1)
3. step_3: [Task description] → tester (depends on: step_2)
4. step_4: [Task description] → reviewer (depends on: step_3)""",
        llm=llm,
    )

    task = 'Build a simple blog API with posts and comments'
    print(f'Task: {task}')
    print('\n🔄 Generating execution plan...')

    try:
        plan_text = await planner.run(f'Create a detailed execution plan for: {task}')
        print('\n📋 Generated Plan:')
        print('-' * 30)
        print(plan_text)

        # Parse into ExecutionPlan object
        execution_plan = PlanParser.parse_plan_from_text(plan_text)

        print('\n✅ Parsed into ExecutionPlan:')
        print(f'Title: {execution_plan.title}')
        print(f'Steps: {len(execution_plan.steps)}')

        for step in execution_plan.steps:
            deps = (
                f" (depends: {', '.join(step.dependencies)})"
                if step.dependencies
                else ''
            )
            print(f'  • {step.id}: {step.description} → {step.agent}{deps}')

    except Exception as e:
        print(f'❌ Error: {e}')


def show_setup_instructions():
    """Show how to set up and run the demo"""
    print('📖 Setup Instructions')
    print('=' * 25)
    print('1. Set your OpenAI API key:')
    print('   export OPENAI_API_KEY=your_api_key_here')
    print('\n2. Run the demo:')
    print('   python examples/live_plan_execute_demo.py')
    print('\n3. Watch the PlanExecuteRouter in action! 🚀')


async def main():
    """Main demo function"""
    print('🎯 Live PlanExecuteRouter Demo with Real OpenAI LLM')
    print('This demo shows the full plan-and-execute workflow with actual API calls!\n')

    if not os.getenv('OPENAI_API_KEY'):
        show_setup_instructions()
        return

    # Run demos
    await run_simple_plan_creation()
    await run_live_demo()

    print('\n\n🎉 Demo Complete!')
    print(
        'You just saw PlanExecuteRouter break down a task and execute it step by step! 🚀'
    )


if __name__ == '__main__':
    asyncio.run(main())
