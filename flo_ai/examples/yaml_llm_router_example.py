"""
Example demonstrating LLM routers in YAML-based Arium workflows.

This example shows how to define LLM routers directly in YAML configuration
without needing to create them programmatically.
"""

import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.llm import OpenAI

# Example YAML configuration with LLM routers
CONTENT_WORKFLOW_YAML = """
metadata:
  name: content-workflow-with-llm-routers
  version: 1.0.0
  description: "Content creation workflow with intelligent LLM-based routing"

arium:
  agents:
    - name: content_creator
      role: Content Creator
      job: >
        You are a content creator. Analyze the input request and create initial content.
        Consider the type of content requested (technical, creative, marketing, etc.)
        and create appropriate base content that can be further processed.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7
        
    - name: technical_writer
      role: Technical Writer
      job: >
        You are a technical writer specializing in documentation, tutorials, and 
        technical content. Refine the content to be clear, accurate, and technically sound.
        Focus on structure, clarity, and technical accuracy.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        
    - name: creative_writer
      role: Creative Writer
      job: >
        You are a creative writer specializing in engaging, storytelling, and 
        creative content. Enhance the content with creativity, compelling narratives,
        and emotional engagement while maintaining the core message.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.8
        
    - name: marketing_writer
      role: Marketing Writer
      job: >
        You are a marketing writer specializing in persuasive, conversion-focused content.
        Optimize the content for engagement, conversion, and brand alignment.
        Focus on clear value propositions and calls to action.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.6
        
    - name: editor
      role: Editor
      job: >
        You are an editor responsible for final review and polishing.
        Review the content for grammar, style, coherence, and overall quality.
        Make final improvements and ensure the content meets high standards.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2

  # LLM Router definitions
  routers:
    - name: content_type_router
      type: smart
      routing_options:
        technical_writer: "Technical content, documentation, tutorials, how-to guides, API docs, technical explanations"
        creative_writer: "Creative writing, storytelling, fiction, poetry, creative marketing, brand narratives"
        marketing_writer: "Marketing content, sales copy, landing pages, email campaigns, product descriptions, ad copy"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        fallback_strategy: first
        
    - name: quality_router
      type: conversation_analysis
      routing_logic:
        editor: "Content that needs final editing and quality review"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        analysis_depth: 2

  workflow:
    start: content_creator
    edges:
      - from: content_creator
        to: [technical_writer, creative_writer, marketing_writer]
        router: content_type_router
      - from: technical_writer
        to: [editor]
        router: quality_router
      - from: creative_writer
        to: [editor]
        router: quality_router
      - from: marketing_writer
        to: [editor]
        router: quality_router
      - from: editor
        to: [end]
    end: [editor]
"""

# Example with task classifier router
TASK_CLASSIFICATION_YAML = """
metadata:
  name: task-classification-workflow
  version: 1.0.0
  description: "Multi-purpose workflow with task classification routing"

arium:
  agents:
    - name: task_analyzer
      role: Task Analyzer
      job: >
        You are a task analyzer. Examine the incoming request and identify
        what type of task it represents. Provide initial analysis and context.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3

    - name: math_solver
      role: Math Solver
      job: >
        You are a mathematics expert. Solve mathematical problems, equations,
        calculations, and provide step-by-step explanations.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1

    - name: code_helper
      role: Code Assistant
      job: >
        You are a programming expert. Help with coding problems, debugging,
        code review, and programming best practices.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2

    - name: general_assistant
      role: General Assistant
      job: >
        You are a general-purpose assistant. Handle various questions,
        provide information, and assist with general tasks.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.5

  routers:
    - name: task_classifier
      type: task_classifier
      task_categories:
        math_solver:
          description: "Mathematical calculations, equations, and problem solving"
          keywords: ["calculate", "solve", "equation", "math", "formula", "arithmetic"]
          examples: ["Calculate 2+2", "Solve x^2 + 5x + 6 = 0", "What is the derivative of x^2?"]
        code_helper:
          description: "Programming, code review, debugging, and software development"
          keywords: ["code", "program", "debug", "function", "class", "algorithm", "python", "javascript"]
          examples: ["Write a Python function", "Debug this code", "Explain this algorithm"]
        general_assistant:
          description: "General questions, information requests, and other tasks"
          keywords: ["what", "how", "explain", "tell me", "help", "information"]
          examples: ["What is the weather like?", "Explain quantum physics", "Help me plan a trip"]
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2

  workflow:
    start: task_analyzer
    edges:
      - from: task_analyzer
        to: [math_solver, code_helper, general_assistant]
        router: task_classifier
      - from: math_solver
        to: [end]
      - from: code_helper
        to: [end]
      - from: general_assistant
        to: [end]
    end: [math_solver, code_helper, general_assistant]
"""


async def run_content_workflow_example():
    """Example 1: Content workflow with smart router"""
    print('🚀 EXAMPLE 1: Content Workflow with Smart LLM Router')
    print('=' * 60)

    # Create workflow from YAML - LLM routers are automatically created!
    builder = AriumBuilder.from_yaml(
        yaml_str=CONTENT_WORKFLOW_YAML,
        base_llm=OpenAI(
            model='gpt-4o-mini', api_key='dummy-key'
        ),  # Dummy key for example
    )

    # Build the workflow
    builder.build()

    # Test with different content types
    test_inputs = [
        'Write a technical tutorial on how to use Docker containers',
        'Create a compelling story about a robot learning to love',
        'Write marketing copy for a new fitness app that helps people stay motivated',
    ]

    for i, test_input in enumerate(test_inputs, 1):
        print(f'\n📝 Test {i}: {test_input}')
        print('-' * 40)

        try:
            # In a real scenario, this would run the workflow
            # For demo purposes, we'll just show the structure
            print('✅ Workflow built successfully with LLM routers!')
            print("   - Router 'content_type_router' will intelligently route to:")
            print('     • technical_writer (for technical content)')
            print('     • creative_writer (for creative content)')
            print('     • marketing_writer (for marketing content)')
            print(
                "   - Router 'quality_router' will route everything to editor for final review"
            )

        except Exception as e:
            print(f'❌ Error: {e}')


async def run_task_classification_example():
    """Example 2: Task classification workflow"""
    print('\n\n🎯 EXAMPLE 2: Task Classification with LLM Router')
    print('=' * 60)

    # Create workflow from YAML
    builder = AriumBuilder.from_yaml(
        yaml_str=TASK_CLASSIFICATION_YAML,
        base_llm=OpenAI(
            model='gpt-4o-mini', api_key='dummy-key'
        ),  # Dummy key for example
    )

    # Build the workflow
    builder.build()

    # Test with different task types
    test_inputs = [
        'Calculate the area of a circle with radius 5',
        'Write a Python function to sort a list',
        'What is the capital of France?',
    ]

    for i, test_input in enumerate(test_inputs, 1):
        print(f'\n🎯 Test {i}: {test_input}')
        print('-' * 40)

        try:
            print('✅ Workflow built successfully with task classifier!')
            print(
                "   - Router 'task_classifier' will intelligently classify and route to:"
            )
            print('     • math_solver (for mathematical problems)')
            print('     • code_helper (for programming tasks)')
            print('     • general_assistant (for general questions)')

        except Exception as e:
            print(f'❌ Error: {e}')


def demonstrate_yaml_schema():
    """Show the YAML schema for LLM routers"""
    print('\n\n📋 LLM Router YAML Schema')
    print('=' * 60)

    schema_example = """
# LLM Router definitions in YAML
routers:
  - name: my_router_name
    type: smart  # Options: smart, task_classifier, conversation_analysis
    
    # For smart routers:
    routing_options:
      option1: "Description of when to route to option1"
      option2: "Description of when to route to option2"
    
    # For task classifier routers:
    task_categories:
      category1:
        description: "What this category handles"
        keywords: ["keyword1", "keyword2"]
        examples: ["Example 1", "Example 2"]
    
    # For conversation analysis routers:
    routing_logic:
      target1: "Logic for routing to target1"
      target2: "Logic for routing to target2"
    
    # Model configuration (optional - uses base_llm if not specified)
    model:
      provider: openai  # openai, anthropic, gemini, ollama
      name: gpt-4o-mini
      base_url: "https://api.openai.com/v1"  # optional
    
    # Router settings (optional)
    settings:
      temperature: 0.3
      fallback_strategy: first  # first, last, random
      analysis_depth: 2  # for conversation_analysis type
"""

    print(schema_example)


async def main():
    """Run all examples"""
    print('🌟 YAML LLM Router Examples')
    print('=' * 80)
    print('This example demonstrates how to define LLM routers directly in YAML!')
    print('No need to create router functions programmatically anymore! 🎉')

    # Show the schema first
    demonstrate_yaml_schema()

    # Run examples
    await run_content_workflow_example()
    await run_task_classification_example()

    print('\n\n🎉 All examples completed!')
    print('=' * 80)
    print('Key benefits of YAML LLM routers:')
    print('✅ Declarative configuration - no code needed')
    print('✅ Easy to modify and version control')
    print('✅ Clear separation of workflow logic and implementation')
    print('✅ Automatic LLM router creation from config')
    print(
        '✅ Support for all router types: smart, task_classifier, conversation_analysis'
    )


if __name__ == '__main__':
    asyncio.run(main())
