"""
Simple variables workflow example with YAML agent configurations.
Demonstrates the same functionality as variables_workflow_example.py but using YAML configs.

This example shows:
1. Simple function to test complete variables (success case) with YAML agents
2. Simple function to test incomplete variables (error case) with YAML agents
3. YAML-based agent configuration instead of direct Agent() instantiation
"""

import os
import asyncio
from flo_ai.builder.agent_builder import AgentBuilder
from flo_ai.arium.builder import AriumBuilder
from flo_ai.llm.gemini_llm import Gemini

from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('GOOGLE_API_KEY')


async def test_single_agent_complete_variables():
    """Test single agent with complete variables"""
    print('\n🟢 TESTING SINGLE AGENT - COMPLETE VARIABLES (YAML)')
    print('-' * 50)

    llm = Gemini(model='gemini-2.5-flash', temperature=0.7, api_key=api_key)

    # Create agent that uses variables (automatically extracted) with YAML
    translator_yaml = """
apiVersion: flo/alpha-v1
metadata:
  name: translator-agent
  version: 1.0.0
  description: "Agent for translating text with specified tone"

agent:
  name: translator
  role: Professional Translator
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a translator. Use this tone <tone>
"""

    translator = AgentBuilder.from_yaml(yaml_str=translator_yaml).with_llm(llm).build()

    # Complete variables
    variables = {
        'target_language': 'Spanish',
        'tone': 'formal',
        'text_to_translate': 'Welcome to our application',
    }

    print('Variables provided:')
    for key, value in variables.items():
        print(f'  ✓ {key}: {value}')

    try:
        result = await translator.run(
            'Translate the following text: <text_to_translate> to <target_language>',
            variables=variables,
        )
        print('\n✅ SUCCESS: Single agent executed successfully!')
        print(f'Result: {result}')
    except Exception as e:
        print(f'❌ Unexpected error: {e}')


async def test_single_agent_incomplete_variables():
    """Test single agent with incomplete variables"""
    print('\n🔴 TESTING SINGLE AGENT - INCOMPLETE VARIABLES (YAML)')
    print('-' * 50)

    llm = Gemini(model='gemini-2.5-flash', temperature=0.7, api_key=api_key)

    # Create agent that uses variables (automatically extracted) with YAML
    calculator_yaml = """
apiVersion: flo/alpha-v1
metadata:
  name: calculator-agent
  version: 1.0.0
  description: "Agent for performing calculations in specified format"

agent:
  name: calculator
  role: Mathematical Calculator
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a calculator. Show the result in <format> format.
"""

    calculator = AgentBuilder.from_yaml(yaml_str=calculator_yaml).with_llm(llm).build()

    # Incomplete variables - missing some required variables
    incomplete_variables = {
        'operation': 'addition',
        'number1': '15',
        # Missing: 'number2' and 'format'
    }

    print('Variables provided:')
    for key, value in incomplete_variables.items():
        print(f'  ✓ {key}: {value}')

    print('\nMissing variables:')
    print('  ❌ number2')
    print('  ❌ format')

    try:
        await calculator.run(
            'Please calculate the result of <operation> of <number1> and <number2>.',
            variables=incomplete_variables,
        )
        print("❌ ERROR: Should have failed but didn't!")
    except ValueError as e:
        print('\n✅ SUCCESS: Expected error caught!')
        print(f'Error message: {e}')


async def test_multi_agent_complete_variables():
    """Test workflow with complete variables - should succeed"""
    print('🟢 TESTING MULTI AGENT - COMPLETE VARIABLES (YAML)')
    print('-' * 40)

    llm = Gemini(model='gemini-2.5-flash', temperature=0.7, api_key=api_key)

    # Agent 1: Content Creator - uses 'topic' and 'style' variables
    content_creator_yaml = """
apiVersion: flo/alpha-v1
metadata:
  name: content-creator-agent
  version: 1.0.0
  description: "Agent for creating content with specified style"

agent:
  name: content_creator
  role: Content Creator
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a content creator. Write in a <style> style. Make it engaging and informative.
"""

    content_creator = (
        AgentBuilder.from_yaml(yaml_str=content_creator_yaml).with_llm(llm).build()
    )

    # Agent 2: Editor - uses 'target_audience' and 'word_limit' variables
    editor_yaml = """
apiVersion: flo/alpha-v1
metadata:
  name: editor-agent
  version: 1.0.0
  description: "Agent for editing content for specific audiences"

agent:
  name: editor
  role: Content Editor
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are an editor. Review and refine the content for <target_audience> audience.
"""

    editor = AgentBuilder.from_yaml(yaml_str=editor_yaml).with_llm(llm).build()

    # Complete variables - all required variables provided
    complete_variables = {
        # Variables for content_creator
        'topic': 'artificial intelligence trends',
        'style': 'professional',
        # Variables for editor
        'target_audience': 'business executives',
        'word_limit': '200',
    }

    print('Variables provided:')
    for key, value in complete_variables.items():
        print(f'  ✓ {key}: {value}')

    try:
        result = await (
            AriumBuilder()
            .add_agents([content_creator, editor])
            .start_with(content_creator)
            .connect(content_creator, editor)
            .end_with(editor)
            .build_and_run(
                inputs=[
                    'Create content about the given topic: <topic>. Keeping it under <word_limit> words.'
                ],
                variables=complete_variables,
            )
        )

        print('\n✅ SUCCESS: Workflow completed with complete variables!')
        print('Final result:')
        for i, message in enumerate(result, 1):
            if isinstance(message, str):
                print(f'  {i}. {message}...')
            else:
                print(f'  {i}. {message}')

    except Exception as e:
        print(f'❌ Unexpected error: {e}')


async def test_multi_agent_incomplete_variables():
    """Test workflow with incomplete variables - should fail with clear error"""
    print('\n🔴 TESTING MULTI AGENT - INCOMPLETE VARIABLES (YAML)')
    print('-' * 40)

    llm = Gemini(model='gemini-2.5-flash', temperature=0.7, api_key=api_key)

    # Agent 1: Researcher - uses 'research_topic' and 'depth_level' variables
    researcher_yaml = """
apiVersion: flo/alpha-v1
metadata:
  name: researcher-agent
  version: 1.0.0
  description: "Agent for conducting research at specified depth"

agent:
  name: researcher
  role: Research Specialist
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a researcher. Research <depth_level> level of detail.
"""

    researcher = AgentBuilder.from_yaml(yaml_str=researcher_yaml).with_llm(llm).build()

    # Agent 2: Summarizer - uses 'summary_format' and 'key_points' variables
    summarizer_yaml = """
apiVersion: flo/alpha-v1
metadata:
  name: summarizer-agent
  version: 1.0.0
  description: "Agent for creating summaries in specified format"

agent:
  name: summarizer
  role: Content Summarizer
  model:
    provider: gemini
    name: gemini-2.5-flash
  settings:
    temperature: 0.7
  job: You are a summarizer. Create a <summary_format> summary.
"""

    summarizer = AgentBuilder.from_yaml(yaml_str=summarizer_yaml).with_llm(llm).build()

    # Incomplete variables - missing several required variables
    incomplete_variables = {
        'research_topic': 'climate change solutions',
        'summary_format': 'bullet_point',
        # Missing: 'depth_level' (for researcher)
        # Missing: 'key_points' (for summarizer)
    }

    print('Variables provided:')
    for key, value in incomplete_variables.items():
        print(f'  ✓ {key}: {value}')

    print('\nMissing variables:')
    print('  ❌ depth_level (required by researcher)')
    print('  ❌ key_points (required by summarizer)')

    try:
        await (
            AriumBuilder()
            .add_agents([researcher, summarizer])
            .start_with(researcher)
            .connect(researcher, summarizer)
            .end_with(summarizer)
            .build_and_run(
                inputs=[
                    'Research the given topic: <research_topic>. Highlight <key_points> key points'
                ],
                variables=incomplete_variables,
            )
        )
        print("❌ ERROR: Should have failed but didn't!")

    except ValueError as e:
        print('\n✅ SUCCESS: Expected error caught!')
        print(f'Error message: {e}')


if __name__ == '__main__':
    print('Available functions to call:')
    print(
        '• asyncio.run(test_single_agent_complete_variables()) - Test single agent complete variables only'
    )
    print(
        '• asyncio.run(test_single_agent_incomplete_variables()) - Test single agent incomplete variables only'
    )
    print(
        '• asyncio.run(test_multi_agent_complete_variables())     - Test multi agent complete variables only'
    )
    print(
        '• asyncio.run(test_multi_agent_incomplete_variables())   - Test multi agent incomplete variables only'
    )
    print()

    asyncio.run(test_single_agent_complete_variables())
    asyncio.run(test_single_agent_incomplete_variables())
    asyncio.run(test_multi_agent_complete_variables())
    asyncio.run(test_multi_agent_incomplete_variables())
