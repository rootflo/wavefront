"""
Example demonstrating PlanExecuteRouter for Cursor-style plan-and-execute workflows.

This example shows how to implement plan-and-execute patterns where tasks are broken down
into sequential steps and executed systematically, similar to how Cursor works.
"""

import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.llm import OpenAI

# Example YAML configuration for Plan-Execute workflow
PLAN_EXECUTE_WORKFLOW_YAML = """
metadata:
  name: plan-execute-development-workflow
  version: 1.0.0
  description: "Cursor-style plan-and-execute workflow for software development"

arium:
  agents:
    - name: planner
      role: Project Planner
      job: >
        You are a project planner who breaks down complex tasks into detailed, sequential steps.
        Create comprehensive execution plans with clear dependencies and assigned agents.
        Output your plan as a structured format that can be executed step by step.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        
    - name: developer
      role: Software Developer
      job: >
        You are a software developer who implements code based on specific requirements.
        Execute development tasks step by step, focusing on clean, maintainable code.
        Report on progress and any issues encountered during implementation.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.5
        
    - name: tester
      role: Quality Assurance Tester
      job: >
        You are a QA tester who validates implementations and ensures quality.
        Test code, identify bugs, and verify that requirements are met.
        Provide detailed feedback on quality and functionality.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        
    - name: reviewer
      role: Code Reviewer
      job: >
        You are a code reviewer who provides final quality assessment.
        Review completed work for best practices, maintainability, and correctness.
        Provide final approval or request additional improvements.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1

  # Plan-Execute router configuration
  routers:
    - name: plan_execute_router
      type: plan_execute
      agents:
        planner: "Creates detailed execution plans by breaking down tasks into sequential steps"
        developer: "Implements code and features according to plan specifications"
        tester: "Tests implementations and validates functionality"
        reviewer: "Reviews and validates completed work for final approval"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        planner_agent: planner
        executor_agent: developer
        reviewer_agent: reviewer

  workflow:
    start: planner
    edges:
      - from: planner
        to: [developer, tester, reviewer, planner]  # All possible destinations
        router: plan_execute_router
      - from: developer
        to: [tester, reviewer, developer, planner]
        router: plan_execute_router
      - from: tester
        to: [developer, reviewer, tester, planner]
        router: plan_execute_router
      - from: reviewer
        to: [end]
    end: [reviewer]
"""

# Simpler Plan-Execute workflow
SIMPLE_PLAN_EXECUTE_YAML = """
metadata:
  name: simple-plan-execute-workflow
  version: 1.0.0
  description: "Simple plan-execute pattern for general tasks"

arium:
  agents:
    - name: planner
      role: Task Planner
      job: >
        Break down the given task into clear, actionable steps.
        Create a detailed plan with dependencies and execution order.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: executor
      role: Task Executor
      job: >
        Execute the steps from the plan one by one.
        Focus on completing each step thoroughly before moving to the next.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: validator
      role: Quality Validator
      job: >
        Validate that all steps have been completed correctly.
        Ensure the final result meets the original requirements.
      model:
        provider: openai
        name: gpt-4o-mini

  routers:
    - name: simple_plan_router
      type: plan_execute
      agents:
        planner: "Creates execution plans"
        executor: "Executes plan steps"
        validator: "Validates results"
      settings:
        planner_agent: planner
        executor_agent: executor
        reviewer_agent: validator

  workflow:
    start: planner
    edges:
      - from: planner
        to: [executor, validator, planner]
        router: simple_plan_router
      - from: executor  
        to: [validator, executor, planner]
        router: simple_plan_router
      - from: validator
        to: [end]
    end: [validator]
"""

# Research workflow with plan-execute pattern
RESEARCH_PLAN_EXECUTE_YAML = """
metadata:
  name: research-plan-execute-workflow
  version: 1.0.0
  description: "Plan-execute workflow for research projects"

arium:
  agents:
    - name: research_planner
      role: Research Planner
      job: >
        Create comprehensive research plans by breaking down research questions
        into specific investigation steps, data collection tasks, and analysis phases.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: researcher
      role: Researcher
      job: >
        Conduct research according to the plan. Gather information, analyze data,
        and document findings for each step of the research plan.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: analyst
      role: Data Analyst
      job: >
        Analyze research data and findings. Identify patterns, draw conclusions,
        and prepare analytical insights based on the collected information.
      model:
        provider: openai
        name: gpt-4o-mini
        
    - name: synthesizer
      role: Research Synthesizer
      job: >
        Synthesize all research findings into a comprehensive final report.
        Ensure all research questions are addressed and conclusions are well-supported.
      model:
        provider: openai
        name: gpt-4o-mini

  routers:
    - name: research_plan_router
      type: plan_execute
      agents:
        research_planner: "Creates detailed research execution plans"
        researcher: "Conducts research and gathers information"
        analyst: "Analyzes data and identifies patterns"
        synthesizer: "Creates final comprehensive reports"
      settings:
        planner_agent: research_planner
        executor_agent: researcher
        reviewer_agent: synthesizer

  workflow:
    start: research_planner
    edges:
      - from: research_planner
        to: [researcher, analyst, synthesizer, research_planner]
        router: research_plan_router
      - from: researcher
        to: [analyst, synthesizer, researcher, research_planner]
        router: research_plan_router
      - from: analyst
        to: [synthesizer, analyst, researcher, research_planner]
        router: research_plan_router
      - from: synthesizer
        to: [end]
    end: [synthesizer]
"""


async def run_development_workflow_example():
    """Example 1: Full development workflow with plan-execute pattern"""
    print('🚀 EXAMPLE 1: Development Workflow with Plan-Execute Pattern')
    print('=' * 65)

    # Create workflow from YAML
    builder = AriumBuilder.from_yaml(
        yaml_str=PLAN_EXECUTE_WORKFLOW_YAML,
        base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),  # Dummy key for demo
    )

    # Build the workflow
    builder.build()

    print('✅ Development workflow built successfully!')
    print('📋 Plan-Execute Pattern: Planner → Developer → Tester → Reviewer')
    print('🎯 The PlanExecuteRouter will:')
    print('   1. Start with planner to create detailed execution plan')
    print('   2. Route to developer for step-by-step implementation')
    print('   3. Route to tester for quality validation')
    print('   4. Route to reviewer for final approval')
    print('   5. Track progress through each step with visual indicators')

    # Test input
    test_input = 'Create a REST API for user authentication with JWT tokens'
    print(f'\n📝 Test Input: {test_input}')
    print('💡 Expected plan steps:')
    print('   ○ Design API endpoints and data models')
    print('   ○ Implement user registration endpoint')
    print('   ○ Implement login endpoint with JWT generation')
    print('   ○ Add authentication middleware')
    print('   ○ Create comprehensive tests')
    print('   ○ Review and optimize code')


async def run_simple_workflow_example():
    """Example 2: Simple plan-execute workflow"""
    print('\n\n🎯 EXAMPLE 2: Simple Plan-Execute Workflow')
    print('=' * 50)

    builder = AriumBuilder.from_yaml(
        yaml_str=SIMPLE_PLAN_EXECUTE_YAML,
        base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )

    builder.build()

    print('✅ Simple workflow built successfully!')
    print('📋 Plan-Execute Pattern: Planner → Executor → Validator')
    print('🎯 Features:')
    print('   • Automatic task breakdown by planner')
    print('   • Sequential step execution')
    print('   • Progress tracking with plan state management')
    print('   • Quality validation before completion')

    test_input = 'Organize a team building event for 20 people'
    print(f'\n📝 Test Input: {test_input}')
    print('💡 Expected workflow:')
    print('   1. Planner creates detailed event plan')
    print('   2. Executor handles each step (venue, catering, activities)')
    print('   3. Validator ensures everything is properly organized')


async def run_research_workflow_example():
    """Example 3: Research workflow with plan-execute pattern"""
    print('\n\n🔬 EXAMPLE 3: Research Plan-Execute Workflow')
    print('=' * 50)

    builder = AriumBuilder.from_yaml(
        yaml_str=RESEARCH_PLAN_EXECUTE_YAML,
        base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )

    builder.build()

    print('✅ Research workflow built successfully!')
    print(
        '📋 Plan-Execute Pattern: Research Planner → Researcher → Analyst → Synthesizer'
    )
    print('🎯 Features:')
    print('   • Structured research methodology')
    print('   • Data collection and analysis phases')
    print('   • Comprehensive synthesis and reporting')
    print('   • Academic-quality research process')

    test_input = 'Research the impact of remote work on employee productivity'
    print(f'\n📝 Test Input: {test_input}')
    print('💡 Expected research plan:')
    print('   ○ Literature review on remote work studies')
    print('   ○ Survey design and data collection')
    print('   ○ Statistical analysis of productivity metrics')
    print('   ○ Qualitative analysis of employee feedback')
    print('   ○ Final report with recommendations')


def demonstrate_plan_execute_features():
    """Show the key features of PlanExecuteRouter"""
    print('\n\n📋 PlanExecuteRouter Key Features')
    print('=' * 45)

    features = """
🎯 Cursor-Style Planning:
   • Automatic task breakdown into sequential steps
   • Dependency tracking between steps
   • Agent assignment for each step
   • Progress visualization with status indicators

📊 Plan Management:
   • ExecutionPlan storage in enhanced memory
   • Step status tracking (pending, in_progress, completed, failed)
   • Automatic next-step determination
   • Failed step recovery and retry logic

🔄 Execution Flow:
   • Phase 1: Planning (create detailed execution plan)
   • Phase 2: Execution (complete steps sequentially)
   • Phase 3: Review (validate final results)
   • Automatic routing between phases

⚙️ Configuration Options:
   • agents: Define available agents and their capabilities
   • planner_agent: Agent responsible for creating plans
   • executor_agent: Default agent for executing steps
   • reviewer_agent: Optional agent for final review

🛡️ Safety Features:
   • Prevents infinite loops with step completion tracking
   • Handles failed steps with recovery mechanisms
   • Memory persistence for plan state
   • Execution context awareness

📝 YAML Configuration:
   ```yaml
   routers:
     - name: plan_execute_router
       type: plan_execute
       agents:
         planner: "Creates execution plans"
         developer: "Implements features"
         tester: "Validates quality"
       settings:
         planner_agent: planner
         executor_agent: developer
         reviewer_agent: tester
   ```

🔧 Memory Integration:
   • Uses PlanAwareMemory for plan storage
   • Automatic plan state persistence
   • Step result tracking and history
   • Context sharing between execution steps
"""

    print(features)


def show_yaml_schema():
    """Show complete YAML schema for PlanExecuteRouter"""
    print('\n\n📄 Complete PlanExecuteRouter YAML Schema')
    print('=' * 55)

    schema = """
# Complete example with PlanExecuteRouter
metadata:
  name: my-plan-execute-workflow
  version: 1.0.0
  description: "Cursor-style plan-and-execute workflow"

arium:
  agents:
    - name: planner
      role: "Task Planner"
      job: "Create detailed execution plans"
      model:
        provider: openai
        name: gpt-4o-mini

    - name: executor
      role: "Task Executor" 
      job: "Execute plan steps systematically"
      model:
        provider: openai
        name: gpt-4o-mini

    - name: reviewer
      role: "Quality Reviewer"
      job: "Review and validate final results"
      model:
        provider: openai
        name: gpt-4o-mini

  routers:
    - name: plan_execute_router
      type: plan_execute                          # Router type
      agents:                                     # Required: Available agents
        planner: "Creates detailed execution plans"
        executor: "Executes individual plan steps"
        reviewer: "Reviews final results"
        specialist: "Handles specialized tasks"
      model:                                      # Optional: LLM for routing
        provider: openai
        name: gpt-4o-mini
      settings:                                   # Optional settings
        temperature: 0.2                         # Router temperature
        planner_agent: planner                   # Agent for creating plans
        executor_agent: executor                 # Default execution agent
        reviewer_agent: reviewer                 # Optional review agent
        max_retries: 3                          # Max retries for failed steps

  workflow:
    start: planner
    edges:
      - from: planner
        to: [executor, reviewer, specialist, planner]    # All possible destinations
        router: plan_execute_router
      - from: executor
        to: [reviewer, specialist, executor, planner]
        router: plan_execute_router
      - from: reviewer
        to: [end]
    end: [reviewer]
"""
    print(schema)


async def main():
    """Run all examples"""
    print('🌟 PlanExecuteRouter Examples - Cursor-Style Plan-and-Execute Workflows')
    print('=' * 85)
    print('This example demonstrates the new PlanExecuteRouter for implementing')
    print('sophisticated plan-and-execute patterns with intelligent step tracking! 🎉')

    # Show features and schema first
    demonstrate_plan_execute_features()
    show_yaml_schema()

    # Run examples
    await run_development_workflow_example()
    await run_simple_workflow_example()
    await run_research_workflow_example()

    print('\n\n🎉 All PlanExecuteRouter examples completed!')
    print('=' * 85)
    print('✅ PlanExecuteRouter Benefits:')
    print('  • Cursor-style automatic task breakdown and execution')
    print('  • Intelligent step-by-step progress tracking')
    print('  • Visual progress indicators with plan state management')
    print('  • Automatic routing based on execution plan progress')
    print('  • Built-in error handling and step retry mechanisms')
    print('  • Enhanced memory system with plan persistence')

    print('\n🚀 Try it yourself:')
    print('  1. Define your planner, executor, and reviewer agents')
    print('  2. Create a plan-execute router with agent mappings')
    print('  3. Use PlanAwareMemory for plan state persistence')
    print('  4. Run complex tasks with automatic breakdown!')


if __name__ == '__main__':
    asyncio.run(main())
