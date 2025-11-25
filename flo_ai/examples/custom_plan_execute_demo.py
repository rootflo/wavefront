"""
Custom Plan-Execute Demo - Creating Your Own Plan Workflows

This demo shows how to create custom plan-execute workflows
using the framework's plan execution components.
"""

import asyncio
import os
from flo_ai.llm import OpenAI
from flo_ai.arium.memory import PlanAwareMemory
from flo_ai.arium.llm_router import create_plan_execute_router
from flo_ai.arium import AriumBuilder
from flo_ai.models import TextMessageContent, UserMessage
from flo_ai.models.plan_agents import PlannerAgent, ExecutorAgent


async def main():
    """Custom plan-execute workflow example"""
    print('🎯 Custom Plan-Execute Demo')
    print('=' * 35)

    # Check API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY environment variable not set')
        return

    # Setup
    llm = OpenAI(model='gpt-4o', api_key=api_key)
    memory = PlanAwareMemory()

    # Create custom agents for research workflow
    planner = PlannerAgent(
        memory=memory,
        llm=llm,
        name='planner',
        system_prompt="""You are a research project planner. Create plans for research tasks.

EXECUTION PLAN: [Title]
DESCRIPTION: [Description]

STEPS:
1. step_1: [Research task] → researcher
2. step_2: [Analysis task] → analyst (depends on: step_1)
3. step_3: [Writing task] → writer (depends on: step_2)

Use agents: researcher, analyst, writer
IMPORTANT: After generating the plan, use store_execution_plan to save it.""",
    )

    researcher = ExecutorAgent(
        memory=memory,
        llm=llm,
        name='researcher',
        system_prompt="""You are a researcher who gathers information and data.
Check plan status first, then execute research steps thoroughly.""",
    )

    analyst = ExecutorAgent(
        memory=memory,
        llm=llm,
        name='analyst',
        system_prompt="""You are an analyst who processes and analyzes research data.
Check plan status first, then execute analysis steps thoroughly.""",
    )

    writer = ExecutorAgent(
        memory=memory,
        llm=llm,
        name='writer',
        system_prompt="""You are a writer who creates reports and summaries.
Check plan status first, then execute writing steps thoroughly.""",
    )

    agents = [planner, researcher, analyst, writer]

    # Create router
    router = create_plan_execute_router(
        planner_agent='planner',
        executor_agent='researcher',
        reviewer_agent='writer',
        additional_agents={'analyst': 'Analyzes research data and findings'},
        llm=llm,
    )

    # Build workflow
    arium = (
        AriumBuilder()
        .with_memory(memory)
        .add_agents(agents)
        .start_with(planner)
        .add_edge(planner, agents, router)
        .add_edge(researcher, agents, router)
        .add_edge(analyst, agents, router)
        .add_edge(writer, agents, router)
        .end_with(writer)
        .build()
    )

    # Execute task
    task = UserMessage(
        TextMessageContent(
            type='text',
            text='Research the impact of AI on software development productivity',
        )
    )
    print(f'📋 Task: {task}')
    print('🔄 Executing custom research workflow...\n')

    try:
        result = await arium.run(task)

        print('\n' + '=' * 40)
        print('🎉 CUSTOM WORKFLOW COMPLETED!')
        print('=' * 40)

        if result:
            final_result = result[-1] if isinstance(result, list) else result
            print(f'\n📄 Final Result:\n{final_result}')

        # Show plan status
        current_plan = memory.get_current_plan()
        if current_plan:
            print(f'\n📊 Plan: {current_plan.title}')
            print(f'✅ Completed: {current_plan.is_completed()}')

    except Exception as e:
        print(f'❌ Error: {e}')


if __name__ == '__main__':
    asyncio.run(main())
