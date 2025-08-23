"""
Fixed PlanExecuteRouter Demo - Resolves the planner loop issue

The previous demo had an issue where the planner kept looping because the plan
wasn't being properly stored in PlanAwareMemory. This version fixes that by:

1. Creating a special PlannerAgent that stores ExecutionPlan objects
2. Ensuring the router can detect when plans are created
3. Proper integration between plan creation and execution phases
"""

import asyncio
import os
import uuid
import re
from flo_ai.models.agent import Agent
from flo_ai.llm import OpenAI
from flo_ai.arium.memory import PlanAwareMemory, ExecutionPlan, PlanStep, StepStatus
from flo_ai.arium.llm_router import create_plan_execute_router
from flo_ai.arium import AriumBuilder


class PlannerAgent(Agent):
    """Special agent that creates ExecutionPlan objects and stores them in memory"""

    def __init__(self, memory: PlanAwareMemory, **kwargs):
        super().__init__(**kwargs)
        self.memory = memory

    async def run(self, input_data, **kwargs):
        """Override run to create and store ExecutionPlan after generating plan text"""

        # First, generate the plan text using the normal agent behavior
        plan_text = await super().run(input_data, **kwargs)

        # Parse the plan text and create ExecutionPlan object
        execution_plan = self._parse_plan_text(plan_text)

        # Store the plan in memory
        if execution_plan:
            self.memory.add_plan(execution_plan)
            print(f'✅ Plan stored in memory: {execution_plan.title}')
            print(f'📊 Steps: {len(execution_plan.steps)}')

            # Show the plan
            for i, step in enumerate(execution_plan.steps, 1):
                deps = (
                    f" (depends: {', '.join(step.dependencies)})"
                    if step.dependencies
                    else ''
                )
                print(f'  {i}. {step.id}: {step.description} → {step.agent}{deps}')

        return plan_text

    def _parse_plan_text(self, plan_text: str) -> ExecutionPlan:
        """Parse LLM-generated plan text into ExecutionPlan object"""

        # Extract title
        title_match = re.search(r'EXECUTION PLAN:\s*(.+)', plan_text)
        title = title_match.group(1).strip() if title_match else 'Generated Plan'

        # Extract description
        desc_match = re.search(r'DESCRIPTION:\s*(.+)', plan_text)
        description = desc_match.group(1).strip() if desc_match else 'Execution plan'

        # Extract steps using regex
        steps = []
        step_pattern = (
            r'(\d+)\.\s*(\w+):\s*(.+?)\s*→\s*(\w+)(?:\s*\(depends on:\s*([^)]+)\))?'
        )

        for match in re.finditer(step_pattern, plan_text, re.MULTILINE):
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
            created_by=self.name,
        )


class ExecutorAgent(Agent):
    """Special agent that marks steps as completed when executing them"""

    def __init__(self, memory: PlanAwareMemory, **kwargs):
        super().__init__(**kwargs)
        self.memory = memory

    async def run(self, input_data, **kwargs):
        """Override run to update step status after execution"""

        # Get current plan and next steps
        current_plan = self.memory.get_current_plan()
        if current_plan:
            next_steps = current_plan.get_next_steps()

            # Find steps assigned to this agent
            my_steps = [step for step in next_steps if step.agent == self.name]

            if my_steps:
                step = my_steps[0]  # Execute first available step
                print(f'⏳ Executing step: {step.id} - {step.description}')

                # Mark step as in progress
                step.status = StepStatus.IN_PROGRESS
                self.memory.update_plan(current_plan)

                # Execute the step using normal agent behavior
                result = await super().run(
                    f'Execute this step: {step.description}. Context: {input_data}',
                    **kwargs,
                )

                # Mark step as completed
                step.status = StepStatus.COMPLETED
                step.result = result
                self.memory.update_plan(current_plan)

                print(f'✅ Completed step: {step.id}')
                return result

        # If no steps to execute, just run normally
        return await super().run(input_data, **kwargs)


async def run_fixed_demo():
    """Run the fixed plan-execute demo"""
    print('🔧 Fixed PlanExecuteRouter Demo')
    print('=' * 40)

    # Check API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY environment variable not set')
        print('   Set it with: export OPENAI_API_KEY=your_key_here')
        return

    print('✅ OpenAI API key found')

    # Create LLM
    llm = OpenAI(model='gpt-4o', api_key=api_key)

    # Create plan-aware memory
    memory = PlanAwareMemory()

    # Create special planner that stores ExecutionPlan objects
    planner = PlannerAgent(
        memory=memory,
        name='planner',
        system_prompt="""You are a project planner. Create execution plans in this EXACT format:

EXECUTION PLAN: [Clear Title]
DESCRIPTION: [Brief description]

STEPS:
1. step_1: [Description] → developer
2. step_2: [Description] → developer (depends on: step_1)
3. step_3: [Description] → tester (depends on: step_2)
4. step_4: [Description] → reviewer (depends on: step_3)

Use only these agents: developer, tester, reviewer
Keep steps clear and actionable.
Always include dependencies where steps must be done in sequence.""",
        llm=llm,
    )

    # Create executor agents that update step status
    developer = ExecutorAgent(
        memory=memory,
        name='developer',
        system_prompt="""You are a developer executing implementation steps.
Provide detailed implementation for the given step.""",
        llm=llm,
    )

    tester = ExecutorAgent(
        memory=memory,
        name='tester',
        system_prompt="""You are a tester validating implementations.
Create test scenarios and validate the implementation.""",
        llm=llm,
    )

    reviewer = Agent(
        name='reviewer',
        system_prompt="""You are a reviewer providing final validation.
Review all completed work and give final approval.""",
        llm=llm,
    )

    print('✅ Created special agents with plan integration')

    # Create plan-execute router
    plan_router = create_plan_execute_router(
        planner_agent='planner',
        executor_agent='developer',
        reviewer_agent='reviewer',
        additional_agents={'tester': 'Tests implementations'},
        llm=llm,
    )

    print('✅ Created PlanExecuteRouter')

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
    task = 'Create a simple user login API endpoint'

    print(f'\n📋 Task: {task}')
    print('\n🔄 Starting fixed plan-execute workflow...')
    print('   This should now properly:')
    print('   1. Create and store execution plan')
    print('   2. Execute steps sequentially')
    print('   3. Track progress through completion')

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

        # Show execution plan status
        current_plan = memory.get_current_plan()
        if current_plan:
            print(f'\n📊 Final Plan Status: {current_plan.title}')
            print(f'Completed: {current_plan.is_completed()}')

            print('\n📋 Step Status:')
            for step in current_plan.steps:
                status_icon = {
                    StepStatus.PENDING: '○',
                    StepStatus.IN_PROGRESS: '⏳',
                    StepStatus.COMPLETED: '✅',
                    StepStatus.FAILED: '❌',
                }.get(step.status, '○')
                print(f'  {status_icon} {step.id}: {step.description} → {step.agent}')
                if step.result:
                    print(f'      Result: {step.result[:100]}...')

        print('\n💡 What was fixed:')
        print('  • PlannerAgent now creates and stores ExecutionPlan objects')
        print('  • ExecutorAgent updates step status during execution')
        print('  • Router can detect when plans exist in memory')
        print('  • No more infinite loops in the planner!')

    except Exception as e:
        print(f'\n❌ Error: {e}')
        print('Check the logs above for more details.')


async def run_simple_test():
    """Run a simple test to verify the fix works"""
    print('\n📋 Simple Plan Creation Test')
    print('=' * 35)

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY not set')
        return

    # Create memory and planner
    memory = PlanAwareMemory()
    llm = OpenAI(model='gpt-4o', api_key=api_key)

    planner = PlannerAgent(
        memory=memory,
        name='planner',
        system_prompt="""Create a plan in this format:

EXECUTION PLAN: [Title]
DESCRIPTION: [Description]

STEPS:
1. step_1: [Task] → developer
2. step_2: [Task] → tester (depends on: step_1)
3. step_3: [Task] → reviewer (depends on: step_2)""",
        llm=llm,
    )

    print('🔄 Testing plan creation and storage...')

    try:
        # Create a plan
        await planner.run('Create a plan for building a simple calculator API')

        # Check if plan was stored
        current_plan = memory.get_current_plan()
        if current_plan:
            print('✅ Plan successfully created and stored!')
            print(f'✅ Title: {current_plan.title}')
            print(f'✅ Steps: {len(current_plan.steps)}')

            # Test next steps
            next_steps = current_plan.get_next_steps()
            print(f'✅ Ready to execute: {len(next_steps)} steps')

            for step in next_steps:
                print(f'   → {step.id}: {step.agent}')
        else:
            print('❌ Plan was not stored in memory')

    except Exception as e:
        print(f'❌ Error: {e}')


def show_fix_explanation():
    """Explain what was fixed"""
    print('\n🔧 What Was Fixed')
    print('=' * 20)

    explanation = """
❌ Problem: Planner Loop
The original demo had the planner stuck in a loop because:
• Planner generated plan text but didn't store ExecutionPlan objects
• Router couldn't detect that a plan existed in memory
• Router kept routing back to planner infinitely

✅ Solution: Special Agent Classes
Created specialized agents that integrate with PlanAwareMemory:
• PlannerAgent: Parses plan text and stores ExecutionPlan objects
• ExecutorAgent: Updates step status during execution
• Proper integration between plan creation and execution

🎯 Key Changes:
1. PlannerAgent.run() now creates and stores ExecutionPlan objects
2. ExecutorAgent.run() marks steps as in-progress/completed
3. Router can detect when plans exist and route accordingly
4. Proper step-by-step execution with status tracking

🚀 Result:
• No more infinite loops
• Proper plan-execute workflow
• Real-time step progress tracking
• Seamless integration with PlanAwareMemory
"""

    print(explanation)


async def main():
    """Main demo function"""
    print('🎯 Fixed PlanExecuteRouter Demo with Real OpenAI LLM')
    print('This version fixes the planner loop issue!\n')

    if not os.getenv('OPENAI_API_KEY'):
        print('❌ OPENAI_API_KEY not set')
        print('   Set it with: export OPENAI_API_KEY=your_key_here')
        return

    # Show what was fixed
    show_fix_explanation()

    # Run tests
    await run_simple_test()
    await run_fixed_demo()

    print('\n\n🎉 Fixed Demo Complete!')
    print('The PlanExecuteRouter now works properly without infinite loops! 🚀')


if __name__ == '__main__':
    asyncio.run(main())
