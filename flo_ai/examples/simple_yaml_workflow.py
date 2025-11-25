"""
Example of running a Flo AI workflow with snake_case agent names
Generated from Flo AI Studio
"""

import asyncio
from flo_ai.arium import AriumBuilder
from flo_ai.tool.base_tool import Tool

# Set your OpenAI API key
# os.environ["OPENAI_API_KEY"] = "your-api-key-here"


# Create a simple web search tool
async def web_search_function(query: str) -> str:
    """Simple web search simulation - replace with actual search API"""
    return f"Web search results for '{query}': Found relevant articles about the topic including latest developments, applications, and ethical considerations. [This is a mock search - integrate with real search API like Google, Bing, or DuckDuckGo]"


# Create the tool instance
web_search_tool = Tool(
    name='web_search',
    description='Search the web for information on a given topic',
    function=web_search_function,
    parameters={
        'query': {
            'type': 'string',
            'description': 'The search query to look up information about',
        }
    },
)

# YAML workflow definition (exported from Flo AI Studio)
workflow_yaml = """
metadata:
  name: New Workflow
  version: 1.0.0
  description: Generated with Flo AI Studio
  tags:
    - flo-ai
    - studio-generated
arium:
  agents:
    - name: content_analyzer
      role: Content Analyst
      job: Analyze content and extract key insights, themes, and important information.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.7
        max_retries: 3
        reasoning_pattern: DIRECT
    - name: researcher
      role: Research Specialist
      job: Research topics and gather comprehensive information using available tools.
      model:
        provider: openai
        name: gpt-4o
      tools:
        - web_search
    - name: summarizer
      role: Summary Generator
      job: Create concise, actionable summaries from analysis and content.
      model:
        provider: openai
        name: gpt-4o-mini
  routers:
    - name: smart_router
      type: smart
      routing_options:
        researcher: If there is not enough information & deep research needs to be done
        summarizer: If we have enough information and its time to summarize
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        fallback_strategy: first
  workflow:
    start: content_analyzer
    edges:
      - from: content_analyzer
        to: [researcher, summarizer]
        router: smart_router
      - from: researcher
        to: [summarizer]
    end:
      - summarizer
"""


async def main():
    """Run the workflow"""
    print('🚀 Starting Flo AI Workflow...')
    print('📋 Workflow: Content Analysis with Smart Routing')
    print('-' * 50)

    try:
        # Create tools dictionary (required format for AriumBuilder)
        tools = {'web_search': web_search_tool}

        # Create Arium builder from YAML
        builder = AriumBuilder.from_yaml(yaml_str=workflow_yaml, tools=tools)

        # Example input for the workflow
        user_input = [
            """I need to understand the current trends in artificial intelligence and machine learning. 
            Specifically, I'm interested in:
            1. Latest developments in large language models
            2. Applications in healthcare and finance
            3. Ethical considerations and regulations
            
            Please provide a comprehensive analysis and summary."""
        ]

        print('📝 Input:')
        print(user_input[0])
        print('\n' + '=' * 50)
        print('🔄 Processing workflow...')
        print('=' * 50 + '\n')

        # Build and run the workflow
        result = await builder.build_and_run(user_input)

        print('✅ Workflow Result:')
        print('-' * 30)
        if isinstance(result, list):
            for i, message in enumerate(result):
                print(f'{i+1}. {message}')
        else:
            print(result)

    except Exception as e:
        print(f'❌ Error running workflow: {str(e)}')
        print('\n💡 Make sure you have:')
        print('1. Set your OPENAI_API_KEY environment variable')
        print('2. Installed flo-ai: pip install flo-ai')
        print('3. All required dependencies')


if __name__ == '__main__':
    asyncio.run(main())
