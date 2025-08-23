"""
Example demonstrating ReflectionRouter for A -> B -> A -> C patterns.

This example shows how to implement a main -> critic -> main -> final reflection workflow
using the new ReflectionRouter with YAML configuration.
"""

import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.llm import OpenAI

# Example YAML configuration for A -> B -> A -> C flow
MAIN_CRITIC_FLOW_YAML = """
metadata:
  name: main-critic-final-workflow
  version: 1.0.0
  description: "A workflow demonstrating A -> B -> A -> C pattern with intelligent flow routing"

arium:
  agents:
    - name: main_agent
      role: Main Agent
      job: >
        You are the main agent responsible for analyzing tasks and creating initial solutions.
        When you receive input, analyze it thoroughly and provide an initial response.
        If you receive feedback from the critic, incorporate it to improve your work.
        Be receptive to criticism and use it to refine your output.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7
        
    - name: critic
      role: Critic Agent
      job: >
        You are a critic agent. Your job is to review the main agent's work and provide
        constructive feedback. Analyze the output for:
        - Accuracy and correctness
        - Completeness and thoroughness
        - Clarity and coherence
        - Areas for improvement
        Provide specific, actionable feedback that the main agent can use to improve.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        
    - name: final_agent
      role: Final Agent
      job: >
        You are the final agent responsible for polishing and finalizing the work.
        Take the refined output from the main agent (after critic feedback) and:
        - Format it professionally
        - Add any final touches or improvements
        - Ensure it meets high quality standards
        - Provide a polished final result
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.5

  # Reflection router configuration for A -> B -> A -> C pattern
  routers:
    - name: main_critic_reflection_router
      type: reflection
      flow_pattern: [main_agent, critic, main_agent, final_agent]
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        allow_early_exit: false
        fallback_strategy: first

  workflow:
    start: main_agent
    edges:
      # Single edge from main_agent using reflection router
      # The router will intelligently route to: critic -> main_agent -> final_agent
      - from: main_agent
        to: [critic, final_agent]  # All possible destinations
        router: main_critic_reflection_router
      - from: critic
        to: [main_agent, final_agent]
        router: main_critic_reflection_router
      - from: final_agent
        to: [end]
    end: [final_agent]
"""

# Alternative stricter flow pattern
STRICT_FLOW_YAML = """
metadata:
  name: strict-main-critic-flow
  version: 1.0.0
  description: "Strict A -> B -> A -> C flow with no deviations allowed"

arium:
  agents:
    - name: writer
      role: Content Writer
      job: >
        You are a content writer. Create initial content based on the user's request.
        Focus on getting the core ideas down first, don't worry about perfection.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.8
        
    - name: reviewer
      role: Content Reviewer
      job: >
        You are a content reviewer. Review the writer's work and provide detailed feedback:
        - What works well
        - What needs improvement
        - Specific suggestions for enhancement
        - Areas that need clarification
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        
    - name: editor
      role: Content Editor
      job: >
        You are the final editor. Take the revised content from the writer and:
        - Polish the language and style
        - Ensure consistency and flow
        - Make final corrections
        - Prepare the content for publication
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3

  routers:
    - name: strict_reflection_router
      type: reflection
      flow_pattern: [writer, reviewer, writer, editor]
      settings:
        allow_early_exit: false  # Strict adherence to pattern
        fallback_strategy: first

  workflow:
    start: writer
    edges:
      - from: writer
        to: [reviewer, editor]
        router: strict_reflection_router
      - from: reviewer
        to: [writer, editor]
        router: strict_reflection_router
      - from: editor
        to: [end]
    end: [editor]
"""

# Flexible flow that allows early exit
FLEXIBLE_FLOW_YAML = """
metadata:
  name: flexible-flow-with-early-exit
  version: 1.0.0
  description: "Flexible A -> B -> A -> C flow that allows early completion"

arium:
  agents:
    - name: analyst
      role: Data Analyst
      job: >
        You are a data analyst. Analyze the given data or question and provide insights.
        Create clear, actionable analysis based on the information provided.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.5
        
    - name: validator
      role: Analysis Validator
      job: >
        You are an analysis validator. Review the analyst's work for:
        - Logical consistency
        - Accuracy of conclusions
        - Completeness of analysis
        - Potential issues or gaps
        If the analysis is solid, you can recommend proceeding directly to completion.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        
    - name: presenter
      role: Results Presenter
      job: >
        You are a results presenter. Take the final analysis and create a professional
        presentation of the findings with clear recommendations and next steps.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.4

  routers:
    - name: flexible_reflection_router
      type: reflection
      flow_pattern: [analyst, validator, analyst, presenter]
      settings:
        allow_early_exit: true  # Allow skipping steps if appropriate
        fallback_strategy: first

  workflow:
    start: analyst
    edges:
      - from: analyst
        to: [validator, presenter]
        router: flexible_reflection_router
      - from: validator
        to: [analyst, presenter]
        router: flexible_reflection_router
      - from: presenter
        to: [end]
    end: [presenter]
"""


async def run_main_critic_flow_example():
    """Example 1: Main -> Critic -> Main -> Final flow"""
    print('🚀 EXAMPLE 1: Main -> Critic -> Main -> Final Flow')
    print('=' * 60)

    # Create workflow from YAML
    builder = AriumBuilder.from_yaml(
        yaml_str=MAIN_CRITIC_FLOW_YAML,
        base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),  # Dummy key for demo
    )

    # Build the workflow
    builder.build()

    print('✅ Workflow built successfully!')
    print('📋 Reflection Pattern: main_agent → critic → main_agent → final_agent')
    print('🎯 The ReflectionRouter will:')
    print('   1. Start with main_agent for initial analysis')
    print('   2. Route to critic for feedback/reflection')
    print('   3. Return to main_agent for improvements')
    print('   4. Finally route to final_agent for polishing')

    # Test input
    test_input = 'Write a comprehensive guide on sustainable urban planning'
    print(f'\n📝 Test Input: {test_input}')
    print('💡 This would follow the strict A→B→A→C pattern automatically!')


async def run_strict_flow_example():
    """Example 2: Strict flow with no deviations"""
    print('\n\n🎯 EXAMPLE 2: Strict Writer -> Reviewer -> Writer -> Editor Flow')
    print('=' * 70)

    builder = AriumBuilder.from_yaml(
        yaml_str=STRICT_FLOW_YAML,
        base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )

    builder.build()

    print('✅ Strict workflow built successfully!')
    print('📋 Flow Pattern: writer → reviewer → writer → editor')
    print('🔒 Features:')
    print('   • Strict adherence to pattern (allow_early_exit: false)')
    print('   • LLM cannot deviate from the A→B→A→C sequence')
    print('   • Execution context tracks progress through flow')

    test_input = 'Create a blog post about renewable energy trends in 2024'
    print(f'\n📝 Test Input: {test_input}')


async def run_flexible_flow_example():
    """Example 3: Flexible flow with early exit option"""
    print('\n\n🌟 EXAMPLE 3: Flexible Flow with Early Exit Option')
    print('=' * 60)

    builder = AriumBuilder.from_yaml(
        yaml_str=FLEXIBLE_FLOW_YAML,
        base_llm=OpenAI(model='gpt-4o-mini', api_key='dummy-key'),
    )

    builder.build()

    print('✅ Flexible workflow built successfully!')
    print('📋 Flow Pattern: analyst → validator → analyst → presenter')
    print('🔓 Features:')
    print('   • Flexible routing (allow_early_exit: true)')
    print('   • LLM can skip steps if analysis is already sufficient')
    print('   • Smart adaptation based on conversation context')

    test_input = 'Analyze the quarterly sales data and identify key trends'
    print(f'\n📝 Test Input: {test_input}')


def demonstrate_reflection_router_features():
    """Show the key features of ReflectionRouter"""
    print('\n\n📋 ReflectionRouter Key Features')
    print('=' * 50)

    features = """
🎯 Reflection Pattern Tracking:
   • Automatically tracks progress through defined reflection sequence
   • Uses execution context (node_visit_count) for intelligent routing
   • Prevents infinite loops while allowing intentional revisits

📊 Visual Progress Display:
   • Shows current position in pattern: ○ pending, ✓ completed
   • Displays suggested next step based on reflection pattern
   • Provides clear feedback on workflow state

⚙️ Configuration Options:
   • allow_early_exit: Enable/disable smart reflection termination
   • flow_pattern: Define exact sequence (e.g., [main, critic, main, final])
   • Standard LLM router settings (temperature, fallback_strategy)

🔄 Execution Context Awareness:
   • Tracks how many times each node has been visited
   • Calculates expected visits based on reflection pattern position
   • Intelligently determines next step in sequence

📝 YAML Configuration:
   ```yaml
   routers:
     - name: my_reflection_router
       type: reflection
       flow_pattern: [main_agent, critic, main_agent, final_agent]
       settings:
         allow_early_exit: false
         temperature: 0.2
   ```

🛡️ Safety Features:
   • Inherits anti-infinite-loop mechanisms from base router
   • Provides clear error messages for configuration issues
   • Graceful fallback when pattern completion detected
"""

    print(features)


def show_yaml_schema():
    """Show complete YAML schema for ReflectionRouter"""
    print('\n\n📄 Complete ReflectionRouter YAML Schema')
    print('=' * 50)

    schema = """
# Complete example with ReflectionRouter
metadata:
  name: my-flow-workflow
  version: 1.0.0
  description: "A -> B -> A -> C flow pattern example"

arium:
  agents:
    - name: main_agent
      role: Main Agent
      job: "Your main agent job description"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7

    - name: critic
      role: Critic
      job: "Your critic agent job description"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3

    - name: final_agent
      role: Final Agent
      job: "Your final agent job description"
      model:
        provider: openai
        name: gpt-4o-mini

  routers:
    - name: reflection_router
      type: reflection                        # Router type
      flow_pattern: [main_agent, critic, main_agent, final_agent]  # A->B->A->C pattern
      model:                                  # Optional: LLM for routing decisions
        provider: openai
        name: gpt-4o-mini
      settings:                               # Optional settings
        temperature: 0.2                      # Router temperature
        allow_early_exit: false               # Allow early completion
        fallback_strategy: first              # first, last, random

  workflow:
    start: main_agent
    edges:
      - from: main_agent
        to: [critic, final_agent]             # All possible destinations
        router: reflection_router             # Use reflection router
      - from: critic
        to: [main_agent, final_agent]
        router: reflection_router
      - from: final_agent
        to: [end]
    end: [final_agent]
"""
    print(schema)


async def main():
    """Run all examples"""
    print('🌟 ReflectionRouter Examples - A → B → A → C Pattern Implementation')
    print('=' * 80)
    print('This example demonstrates the new ReflectionRouter for implementing')
    print('structured reflection patterns with intelligent LLM-based routing! 🎉')

    # Show features and schema first
    demonstrate_reflection_router_features()
    show_yaml_schema()

    # Run examples
    await run_main_critic_flow_example()
    await run_strict_flow_example()
    await run_flexible_flow_example()

    print('\n\n🎉 All ReflectionRouter examples completed!')
    print('=' * 80)
    print('✅ ReflectionRouter Benefits:')
    print('  • Simple YAML configuration for complex reflection patterns')
    print('  • Automatic progress tracking through execution context')
    print('  • Intelligent routing decisions based on reflection state')
    print('  • Flexible vs strict reflection control options')
    print('  • Built-in safety features and loop prevention')
    print('  • Easy integration with existing Arium workflows')

    print('\n🚀 Try it yourself:')
    print('  1. Define your agents (main, critic, final)')
    print('  2. Create a reflection router with your pattern')
    print('  3. Configure workflow edges')
    print('  4. Run your A→B→A→C reflection workflow!')


if __name__ == '__main__':
    asyncio.run(main())
