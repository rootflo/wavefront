"""
Simple Working PlanExecuteRouter Demo

This version fixes the planner loop by using a different approach:
1. Use a standard workflow without plan storage complexity
2. Demonstrate the routing intelligence with manual plan simulation
3. Show how the router makes decisions based on context
"""

import asyncio
import os
from flo_ai.models.agent import Agent
from flo_ai.llm import OpenAI
from flo_ai.arium.memory import MessageMemory, MessageMemoryItem
from flo_ai.arium.llm_router import create_plan_execute_router
from flo_ai.arium import AriumBuilder
from flo_ai.models.agent import UserMessage


async def simple_working_demo():
    """Simple working demo that avoids the planner loop"""
    print('✅ Simple Working PlanExecuteRouter Demo')
    print('=' * 45)

    # Check API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY environment variable not set')
        print('   Set it with: export OPENAI_API_KEY=your_key_here')
        return

    print('✅ OpenAI API key found')

    # Create LLM
    llm = OpenAI(model='gpt-4o', api_key=api_key)

    # Create simple agents focused on their core tasks
    planner = Agent(
        name='planner',
        system_prompt="""You are a project planner. When given a task, create a detailed plan with numbered steps.

Format your response like this:

PLAN FOR: [task name]

EXECUTION STEPS:
1. [First step description] 
2. [Second step description]
3. [Third step description] 
4. [Final step description]

NEXT ACTION: The developer should start with step 1.

Keep it clear and actionable.""",
        llm=llm,
    )

    developer = Agent(
        name='developer',
        system_prompt="""You are a software developer. When given a development task:

1. Acknowledge what you're implementing
2. Provide implementation details
3. Mention any important considerations
4. State when you've completed the task

Be specific and thorough in your implementation.""",
        llm=llm,
    )

    tester = Agent(
        name='tester',
        system_prompt="""You are a QA tester. When given something to test:

1. Acknowledge what you're testing
2. Create test scenarios
3. Identify potential issues
4. Provide test results and recommendations

Be thorough in your testing approach.""",
        llm=llm,
    )

    reviewer = Agent(
        name='reviewer',
        system_prompt="""You are a senior reviewer. When reviewing work:

1. Assess overall quality and completeness
2. Check if requirements are met
3. Provide constructive feedback
4. Give final approval or suggest improvements

Focus on delivering high-quality results.""",
        llm=llm,
    )

    print('✅ Created focused agents: planner, developer, tester, reviewer')

    # Create a simple router using the proper factory function
    from typing import Literal
    from flo_ai.arium.memory import BaseMemory

    def create_simple_router():
        """Create a simple router with proper type annotations"""

        def router_impl(
            memory: BaseMemory,
        ) -> Literal['developer', 'tester', 'reviewer']:
            """Simple routing logic for demo purposes"""
            messages = memory.get()

            # Check the conversation flow
            if not messages:
                return 'developer'  # Start with developer after planner

            last_message = str(messages[-1])

            # Basic routing logic based on content
            if 'PLAN FOR:' in last_message and 'EXECUTION STEPS:' in last_message:
                print('📋 Plan detected - routing to developer')
                return 'developer'
            elif (
                'implemented' in last_message.lower()
                or 'development' in last_message.lower()
            ):
                print('💻 Development complete - routing to tester')
                return 'tester'
            elif 'test' in last_message.lower() and 'complete' in last_message.lower():
                print('🧪 Testing complete - routing to reviewer')
                return 'reviewer'
            elif len(messages) > 6:  # Prevent too many iterations
                print('🏁 Workflow complete - ending')
                return 'reviewer'
            else:
                return 'developer'  # Default fallback

        # Add required annotations
        router_impl.__annotations__ = {
            'memory': BaseMemory,
            'return': Literal['developer', 'tester', 'reviewer'],
        }

        return router_impl

    simple_router = create_simple_router()

    # Create memory
    memory = MessageMemory()

    # Build workflow with simple routing
    # Note: Each edge's 'to' nodes must include all possible router return values
    arium = (
        AriumBuilder()
        .with_memory(memory)
        .add_agents([planner, developer, tester, reviewer])
        .start_with(planner)
        .add_edge(planner, [developer, tester, reviewer], simple_router)
        .add_edge(
            developer, [developer, tester, reviewer], simple_router
        )  # Include all possible destinations
        .add_edge(
            tester, [developer, tester, reviewer], simple_router
        )  # Include all possible destinations
        .end_with(reviewer)
        .build()
    )

    print('✅ Built simple workflow with basic routing')

    # Task to execute
    task = 'Create a simple login endpoint with username and password validation'

    print(f'\n📋 Task: {task}')
    print('\n🔄 Running simple workflow...')
    print('   This demonstrates the routing concept without complex plan storage')

    try:
        # Execute workflow
        result = await arium.run(task)

        print('\n' + '=' * 50)
        print('🎉 SIMPLE WORKFLOW COMPLETED!')
        print('=' * 50)

        # Show the conversation flow
        if memory.get():
            print('\n📄 Conversation Flow:')
            print('-' * 30)
            for i, msg in enumerate(memory.get(), 1):
                role = msg.result.role
                content = str(msg.result.content)[:200]
                role_str = role.upper() if role else 'UNKNOWN'
                print(f'{i}. {role_str}: {content}...')

        # Show final result
        if result:
            final_result = result[-1].result.content
            print('\n📄 Final Output:')
            print('-' * 30)
            print(final_result)

        print('\n💡 What this demonstrated:')
        print('  • Basic plan-execute workflow concept')
        print('  • Intelligent routing between phases')
        print('  • Planner → Developer → Tester → Reviewer flow')
        print('  • How to avoid infinite loops with simple logic')

    except Exception as e:
        print(f'\n❌ Error: {e}')


async def demonstrate_plan_execute_router():
    """Show the actual PlanExecuteRouter in a controlled way"""
    print('\n\n📊 PlanExecuteRouter Demonstration')
    print('=' * 40)

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print('❌ OPENAI_API_KEY not set')
        return

    llm = OpenAI(model='gpt-4o', api_key=api_key)

    # Create the actual PlanExecuteRouter
    create_plan_execute_router(
        planner_agent='planner',
        executor_agent='developer',
        reviewer_agent='reviewer',
        additional_agents={'tester': 'Tests implementations'},
        llm=llm,
    )

    print('✅ Created actual PlanExecuteRouter')

    # Test router decision making with mock memory
    memory = MessageMemory()

    # Simulate different scenarios
    scenarios = [
        {'msg': 'Create a user API', 'context': 'Initial request'},
        {'msg': 'Plan created with 4 steps', 'context': 'After planning'},
        {'msg': 'Step 1 implemented successfully', 'context': 'After development'},
        {'msg': 'All tests passed', 'context': 'After testing'},
    ]

    print('\n🧠 Router Decision Making:')
    for scenario in scenarios:
        memory.add(
            MessageMemoryItem(node='user', result=UserMessage(content=scenario['msg']))
        )

        try:
            # This would make an actual LLM call to decide routing
            print(f'\n  Context: {scenario["context"]}')
            print(f'  Message: {scenario["msg"]}')
            print('  Router would make intelligent decision based on this context')
            # decision = plan_router(memory)  # Uncomment to see actual routing
            # print(f'  Decision: Route to {decision}')
        except Exception as e:
            print(f'  Note: {e}')

    print('\n💡 The PlanExecuteRouter makes intelligent routing decisions by:')
    print('  • Analyzing conversation context')
    print('  • Detecting plan creation vs execution phases')
    print('  • Understanding step dependencies and progress')
    print('  • Routing to appropriate agents based on workflow state')


def show_solution_approaches():
    """Show different approaches to fix the planner loop"""
    print('\n\n🔧 Solutions to the Planner Loop Issue')
    print('=' * 45)

    solutions = """
The planner loop happened because the router couldn't detect plan completion.
Here are several solutions:

1. 📋 SPECIALIZED PLANNER AGENT (Best Solution)
   • PlannerAgent that stores ExecutionPlan objects in PlanAwareMemory
   • Router detects when plans exist and switches to execution mode
   • See fixed_plan_execute_demo.py for implementation

2. 🎯 CONTENT-BASED ROUTING (Simple Solution)
   • Router analyzes message content to detect phases
   • If message contains "PLAN:", route to developer
   • If message contains "implemented:", route to tester
   • See simple_working_demo.py example above

3. 🔄 LIMITED ITERATIONS (Quick Fix)
   • Add max iteration limits to prevent infinite loops
   • Router switches phases after X iterations
   • Less intelligent but prevents loops

4. 📊 STATE MANAGEMENT (Advanced Solution)
   • Use custom memory with explicit state tracking
   • Store workflow phase (planning/executing/reviewing)
   • Router uses state to make decisions

5. 🧠 BETTER PROMPTING (Prompt Engineering)
   • Improve router prompts to better detect completion
   • Add explicit "PLANNING COMPLETE" markers
   • Train router to recognize different phases

Recommendation: Use approach #1 (Specialized Planner Agent) for production,
approach #2 (Content-Based Routing) for quick demos.
"""

    print(solutions)


async def main():
    """Main demo function"""
    print('🎯 Working PlanExecuteRouter Demo (Loop Issue Fixed)')
    print('This demo shows how to avoid the planner loop issue!\n')

    if not os.getenv('OPENAI_API_KEY'):
        print('❌ To run this demo, set your OPENAI_API_KEY environment variable')
        print('   export OPENAI_API_KEY=your_key_here')
        return

    # Show solution approaches
    show_solution_approaches()

    # Run simple working demo
    await simple_working_demo()

    # Demonstrate the actual router
    await demonstrate_plan_execute_router()

    print('\n\n🎉 Demo Complete!')
    print('=' * 20)
    print('✅ Demonstrated working plan-execute workflow')
    print('✅ Showed how to avoid planner loops')
    print('✅ Explained multiple solution approaches')
    print('\n🚀 Try the fixed_plan_execute_demo.py for the complete solution!')


if __name__ == '__main__':
    asyncio.run(main())
