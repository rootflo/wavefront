#!/usr/bin/env python3
"""
Example demonstrating LLM-powered routing in Arium workflows.

This example shows different ways to use intelligent routing where the LLM
makes decisions about which agent should handle the next step in the workflow.
"""

import asyncio
import os
from typing import Literal

from flo_ai.arium import AriumBuilder, create_llm_router, llm_router
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.llm import OpenAI
from flo_ai.models.base_agent import ReasoningPattern
from flo_ai.arium.memory import BaseMemory


# Set up environment
# Make sure to set your OpenAI API key
# export OPENAI_API_KEY=your_api_key_here


async def example_1_smart_router():
    """
    Example 1: Using create_llm_router for a research workflow
    """
    print('=' * 60)
    print('EXAMPLE 1: Smart LLM Router')
    print('=' * 60)

    llm = OpenAI(model='gpt-4o-mini')

    # Create an intelligent router using the factory function
    intelligent_router = create_llm_router(
        'smart',
        routing_options={
            'researcher': 'Gather information and conduct research on topics',
            'analyst': 'Analyze data, perform calculations, and provide data-driven insights',
            'summarizer': 'Create summaries, conclusions, and final reports',
        },
        context_description='a research and analysis workflow',
        llm=llm,
    )

    # Build workflow with YAML-like structure
    workflow_yaml = """
    metadata:
      name: intelligent-research-workflow
      version: 1.0.0
      description: "Research workflow with LLM-powered routing"
    
    arium:
      agents:
        - name: classifier
          role: "Task Coordinator"
          job: "Analyze incoming tasks and coordinate the workflow by deciding what type of work is needed."
          model:
            provider: openai
            name: gpt-4o-mini
          settings:
            temperature: 0.3
            
        - name: researcher
          role: "Research Specialist"
          job: "Gather comprehensive information and conduct thorough research."
          model:
            provider: openai
            name: gpt-4o-mini
            
        - name: analyst
          role: "Data Analyst"
          job: "Analyze data and provide insights."
          model:
            provider: openai
            name: gpt-4o-mini
            
        - name: summarizer
          role: "Summary Specialist"
          job: "Create final summaries and reports."
          model:
            provider: openai
            name: gpt-4o-mini
      
      workflow:
        start: classifier
        edges:
          - from: classifier
            to: [researcher, analyst, summarizer]
            router: intelligent_router
          - from: researcher
            to: [summarizer]
          - from: analyst
            to: [summarizer]
        end: [summarizer]
    """

    # Create the workflow
    result = await (
        AriumBuilder()
        .from_yaml(
            yaml_str=workflow_yaml, routers={'intelligent_router': intelligent_router}
        )
        .build_and_run(
            [
                'I need to understand the current state of renewable energy adoption globally. '
                'Please provide statistics, trends, and market analysis for solar and wind energy.'
            ]
        )
    )

    print('Result:')
    for i, message in enumerate(result):
        print(f'{i+1}. {message}')

    return result


async def example_2_decorator_router():
    """
    Example 2: Using the @llm_router decorator
    """
    print('\n' + '=' * 60)
    print('EXAMPLE 2: LLM Router Decorator')
    print('=' * 60)

    llm = OpenAI(model='gpt-4o-mini')

    # Define a router using the decorator with better routing logic
    @llm_router(
        {
            'editor': 'Edit and improve the content if it needs refinement (max 2 editing rounds)',
            'reviewer': 'Move to final review and approval when content is ready',
        },
        llm=llm,
        context_description='a content creation workflow that should progress to review after 1-2 editing rounds',
    )
    def content_workflow_router(memory: BaseMemory) -> Literal['editor', 'reviewer']:
        """Smart router for content creation workflow"""
        pass  # Implementation provided by decorator

    # Create agents
    content_creator = (
        AgentBuilder()
        .with_name('content_creator')
        .with_prompt(
            'You are a creative content creator. Write engaging, original content on any topic.'
        )
        .with_llm(llm)
        .build()
    )

    editor = (
        AgentBuilder()
        .with_name('editor')
        .with_prompt(
            'You are a professional editor. Improve content clarity, flow, and structure.'
        )
        .with_llm(llm)
        .build()
    )

    reviewer = (
        AgentBuilder()
        .with_name('reviewer')
        .with_prompt(
            'You are a quality reviewer. Provide final review and approval of content.'
        )
        .with_llm(llm)
        .build()
    )

    # Build workflow with progressive structure (no loops back to previous stages)
    result = await (
        AriumBuilder()
        .add_agents([content_creator, editor, reviewer])
        .start_with(content_creator)
        .add_edge(
            content_creator, [editor, reviewer], content_workflow_router
        )  # Content creator can only go forward
        .add_edge(
            editor, [reviewer]
        )  # Editor always goes to reviewer (no router needed for single destination)
        .end_with(reviewer)
        .build_and_run(
            [
                'Write a blog post about the benefits of remote work for software developers. '
                'Make it engaging and include practical tips.'
            ]
        )
    )

    print('Result:')
    for i, message in enumerate(result):
        print(f'{i+1}. {message}')

    return result


async def example_3_task_classifier_router():
    """
    Example 3: Using TaskClassifierRouter for specialized routing
    """
    print('\n' + '=' * 60)
    print('EXAMPLE 3: Task Classifier Router')
    print('=' * 60)

    llm = OpenAI(model='gpt-4o-mini')

    # Create a task classifier router
    task_router = create_llm_router(
        'task_classifier',
        task_categories={
            'math_specialist': {
                'description': 'Handle mathematical calculations, statistics, and numerical analysis',
                'keywords': [
                    'calculate',
                    'math',
                    'number',
                    'statistics',
                    'compute',
                    'formula',
                ],
                'examples': [
                    'Calculate the average of these numbers',
                    "What's the statistical significance?",
                    'Compute the growth rate',
                ],
            },
            'text_specialist': {
                'description': 'Handle text analysis, writing, and language tasks',
                'keywords': [
                    'write',
                    'text',
                    'analyze',
                    'grammar',
                    'language',
                    'content',
                ],
                'examples': [
                    'Analyze this text for sentiment',
                    'Write a summary of this document',
                    'Check grammar and style',
                ],
            },
            'research_specialist': {
                'description': 'Handle research, fact-checking, and information gathering',
                'keywords': [
                    'research',
                    'find',
                    'investigate',
                    'facts',
                    'information',
                    'search',
                ],
                'examples': [
                    'Research the latest trends in AI',
                    'Find information about this company',
                    'Investigate the causes of climate change',
                ],
            },
        },
        llm=llm,
    )

    # Create specialized agents
    math_specialist = (
        AgentBuilder()
        .with_name('math_specialist')
        .with_prompt(
            'You are a mathematics expert. Handle all calculations, statistical analysis, and numerical computations.'
        )
        .with_llm(llm)
        .with_reasoning(ReasoningPattern.COT)
        .build()
    )

    text_specialist = (
        AgentBuilder()
        .with_name('text_specialist')
        .with_prompt(
            'You are a text analysis expert. Handle writing, editing, and language-related tasks.'
        )
        .with_llm(llm)
        .build()
    )

    research_specialist = (
        AgentBuilder()
        .with_name('research_specialist')
        .with_prompt(
            'You are a research expert. Gather information, verify facts, and provide comprehensive research.'
        )
        .with_llm(llm)
        .build()
    )

    # Test different types of tasks
    test_tasks = [
        'Calculate the compound annual growth rate for an investment that grew from $1000 to $1500 over 3 years.',
        'Research the current market leaders in electric vehicle manufacturing and their market share.',
        "Analyze this text for sentiment and writing quality: 'The new product launch was a tremendous success, exceeding all expectations and delighting customers worldwide.'",
    ]

    for i, task in enumerate(test_tasks):
        print(f'\nTask {i+1}: {task}')

        result = await (
            AriumBuilder()
            .add_agents([math_specialist, text_specialist, research_specialist])
            .start_with(math_specialist)  # Start node (will be routed immediately)
            .add_edge(
                math_specialist,
                [math_specialist, text_specialist, research_specialist],
                task_router,
            )
            .add_edge(
                text_specialist,
                [math_specialist, text_specialist, research_specialist],
                task_router,
            )
            .add_edge(
                research_specialist,
                [math_specialist, text_specialist, research_specialist],
                task_router,
            )
            .end_with(math_specialist)
            .end_with(text_specialist)
            .end_with(research_specialist)
            .build_and_run([task])
        )

        print(f'Result: {result[-1]}')


async def example_4_conversation_analysis_router():
    """
    Example 4: Using ConversationAnalysisRouter for flow-based routing
    """
    print('\n' + '=' * 60)
    print('EXAMPLE 4: Conversation Analysis Router')
    print('=' * 60)

    llm = OpenAI(model='gpt-4o-mini')

    # Create a conversation analysis router
    flow_router = create_llm_router(
        'conversation_analysis',
        routing_logic={
            'planner': 'Route here when starting a new task or when planning is needed',
            'executor': "Route here when there's a clear plan and work needs to be executed",
            'reviewer': 'Route here when work is complete and needs review or when ready to finalize',
        },
        analysis_depth=3,  # Analyze last 3 messages
        llm=llm,
    )

    # Create agents
    planner = (
        AgentBuilder()
        .with_name('planner')
        .with_prompt(
            'You are a strategic planner. Break down complex tasks into actionable plans and next steps.'
        )
        .with_llm(llm)
        .build()
    )

    executor = (
        AgentBuilder()
        .with_name('executor')
        .with_prompt(
            'You are a task executor. Follow plans and complete specific work items with attention to detail.'
        )
        .with_llm(llm)
        .build()
    )

    reviewer = (
        AgentBuilder()
        .with_name('reviewer')
        .with_prompt(
            'You are a quality reviewer. Review completed work and provide final assessment and recommendations.'
        )
        .with_llm(llm)
        .build()
    )

    # Build and run workflow
    result = await (
        AriumBuilder()
        .add_agents([planner, executor, reviewer])
        .start_with(planner)
        .add_edge(planner, [planner, executor, reviewer], flow_router)
        .add_edge(executor, [planner, executor, reviewer], flow_router)
        .end_with(reviewer)
        .build_and_run(
            [
                'I need to create a comprehensive marketing strategy for launching a new mobile app. '
                'The app is a personal finance tracker targeting millennials.'
            ]
        )
    )

    print('Result:')
    for i, message in enumerate(result):
        print(f'{i+1}. {message}')

    return result


async def main():
    """Run all LLM router examples"""
    try:
        print('🚀 LLM-Powered Router Examples')
        print(
            'These examples demonstrate intelligent routing using Large Language Models'
        )
        print('to make dynamic decisions about workflow progression.\n')

        # Run examples
        await example_1_smart_router()
        await example_2_decorator_router()
        await example_3_task_classifier_router()
        await example_4_conversation_analysis_router()

        print('\n' + '=' * 60)
        print('🎉 ALL LLM ROUTER EXAMPLES COMPLETED!')
        print('=' * 60)
        print('\n📋 Examples demonstrated:')
        print('   • Smart router with factory function')
        print('   • Decorator-based router definition')
        print('   • Task classifier for specialized routing')
        print('   • Convenience functions for common patterns')
        print('   • Conversation analysis for flow-based routing')
        print('\n💡 Key benefits:')
        print('   • Dynamic routing based on content analysis')
        print('   • Context-aware workflow progression')
        print('   • Reduced need for complex conditional logic')
        print('   • Self-adapting workflows')

    except Exception as e:
        print(f'❌ Error running examples: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    # Make sure you have set your OpenAI API key
    if not os.getenv('OPENAI_API_KEY'):
        print('⚠️  Warning: OPENAI_API_KEY environment variable not set!')
        print('   Set it with: export OPENAI_API_KEY=your_api_key_here')
        print('   Some examples may fail without a valid API key.\n')

    asyncio.run(main())
