"""
Example demonstrating YAML-based Arium workflow construction.

This example shows how to define multi-agent workflows using YAML configuration
instead of programmatic builder patterns.
"""

import asyncio
from typing import Dict, Literal, Callable, Optional
from flo_ai.arium.builder import AriumBuilder
from flo_ai.arium.memory import MessageMemoryItem
from flo_ai.models import UserMessage
from flo_ai.tool.base_tool import Tool
from flo_ai.llm import OpenAI
from flo_ai.arium.memory import BaseMemory
from typing import List


# Example YAML configuration for a simple linear workflow (using direct agent definition)
SIMPLE_WORKFLOW_YAML = """
metadata:
  name: simple-analysis-workflow
  version: 1.0.0
  description: "A simple two-agent workflow for content analysis"

arium:
  agents:
    - name: content_analyst
      role: Content Analyst
      job: >
        You are a content analyst. When you receive input, analyze it and provide:
        1. A brief summary of the content
        2. The main topics covered
        3. Any insights or observations
        
        Pass your analysis to the next agent for final processing.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        max_retries: 3
        
    - name: summary_generator
      role: Summary Generator
      job: >
        You are a summary generator. You receive analysis from the content analyst.
        Your job is to create a concise, well-structured final summary that includes:
        1. Key takeaways
        2. Actionable insights
        3. A clear conclusion
        
        Make your response clear and professional.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        
  workflow:
    start: content_analyst
    edges:
      - from: content_analyst
        to: [summary_generator]
      - from: summary_generator
        to: [end]
    end: [summary_generator]
"""


# Example YAML configuration with tools and conditional routing (using direct agent definition)
COMPLEX_WORKFLOW_YAML = """
metadata:
  name: research-workflow
  version: 1.0.0
  description: "A complex workflow with tools and conditional routing"

arium:
  agents:
    - name: researcher
      role: Research Analyst
      job: >
        You are a research analyst. Analyze the input and determine if you need to:
        1. Use the calculator tool for mathematical analysis
        2. Use the text processor for text analysis
        3. Or proceed directly to the final summarizer
        
        Based on your analysis, decide the appropriate next step.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        reasoning_pattern: REACT
        
    - name: math_specialist
      role: Mathematics Specialist
      job: >
        You are a mathematics specialist. Use the calculator tool to perform
        mathematical calculations and provide detailed analysis of the results.
      model:
        provider: openai
        name: gpt-4o-mini
      tools: ["calculator"]
      settings:
        reasoning_pattern: REACT
        
    - name: text_specialist
      role: Text Analysis Specialist  
      job: >
        You are a text analysis specialist. Use the text processor tool to
        analyze text content and provide insights about the text structure and content.
      model:
        provider: openai
        name: gpt-4o-mini
      tools: ["text_processor"]
      settings:
        reasoning_pattern: REACT
        
    - name: final_summarizer
      role: Final Summarizer
      job: >
        You are the final summarizer. Take all previous analysis and create 
        a comprehensive final report based on the work done by previous agents.
      model:
        provider: openai
        name: gpt-4o-mini
        
  workflow:
    start: researcher
    edges:
      - from: researcher
        to: [math_specialist, text_specialist, final_summarizer]
        router: research_router
      - from: math_specialist
        to: [final_summarizer]
      - from: text_specialist
        to: [final_summarizer]
      - from: final_summarizer
        to: [end]
    end: [final_summarizer]
"""


# Example YAML configuration with function nodes
FUNCTION_NODES_WORKFLOW_YAML = """
metadata:
  name: function-nodes-workflow
  version: 1.0.0
  description: "A workflow demonstrating function nodes for data processing"

arium:
  agents:
    - name: data_analyzer
      role: Data Analyzer
      job: >
        You are a data analyzer. Analyze the input data and extract key information.
        Pass the analyzed data to the next processing step.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        
    - name: report_formatter
      role: Report Formatter
      job: >
        You are a report formatter. Take the processed data and format it into
        a well-structured final report.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
        
  function_nodes:
    - name: data_validator
      function_name: validate_data
      description: "Validates and cleans input data"
      
    - name: data_transformer
      function_name: transform_data
      description: "Transforms data into a structured format"
      
  workflow:
    start: data_analyzer
    edges:
      - from: data_analyzer
        to: [data_validator]
      - from: data_validator
        to: [data_transformer]
      - from: data_transformer
        to: [report_formatter]
      - from: report_formatter
        to: [end]
    end: [report_formatter]
"""


# Example YAML configuration mixing agents, function nodes, and routing
MIXED_NODES_WORKFLOW_YAML = """
metadata:
  name: mixed-nodes-workflow
  version: 1.0.0
  description: "A workflow mixing agents, function nodes, and conditional routing"

arium:
  agents:
    - name: dispatcher
      role: Workflow Dispatcher
      job: >
        You are a workflow dispatcher. Analyze the input and determine the appropriate
        processing path: mathematical operations, text processing, or direct summarization.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        reasoning_pattern: REACT
        
    - name: math_agent
      role: Mathematics Agent
      job: >
        You are a mathematics agent. Perform mathematical analysis and calculations
        on the provided data.
      model:
        provider: openai
        name: gpt-4o-mini
      tools: ["calculator"]
      settings:
        reasoning_pattern: REACT
        
    - name: text_agent
      role: Text Processing Agent
      job: >
        You are a text processing agent. Analyze and process text content.
      model:
        provider: openai
        name: gpt-4o-mini
      tools: ["text_processor"]
      settings:
        reasoning_pattern: REACT
        
    - name: final_summarizer
      role: Final Summarizer
      job: >
        You are the final summarizer. Create a comprehensive summary of all processing results.
      model:
        provider: openai
        name: gpt-4o-mini
        
  function_nodes:
    - name: preprocessor
      function_name: preprocess_input
      description: "Preprocesses input data before agent processing"
      
    - name: result_aggregator
      function_name: aggregate_results
      description: "Aggregates results from multiple processing paths"
      
  workflow:
    start: dispatcher
    edges:
      - from: dispatcher
        to: [preprocessor]
      - from: preprocessor
        to: [math_agent, text_agent, final_summarizer]
        router: dispatch_router
      - from: math_agent
        to: [result_aggregator]
      - from: text_agent
        to: [result_aggregator]
      - from: result_aggregator
        to: [final_summarizer]
      - from: final_summarizer
        to: [end]
    end: [final_summarizer]
"""


# Example showing mixed configuration approaches
MIXED_CONFIG_YAML = """
metadata:
  name: mixed-configuration-example
  version: 1.0.0
  description: "Example showing different agent configuration methods"

arium:
  agents:
    # Method 1: Direct configuration (new approach)
    - name: input_validator
      role: Input Validator
      job: "Validate and preprocess the input data"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.1
        max_retries: 2
        
    # Method 2: Inline YAML configuration (existing approach)
    - name: data_processor
      yaml_config: |
        agent:
          name: data_processor
          role: Data Processor
          job: >
            Process the validated data using advanced analytics
            and prepare it for final reporting.
          model:
            provider: openai
            name: gpt-4o-mini
          settings:
            temperature: 0.3
            reasoning_pattern: COT
            
    # Method 3: Direct configuration with structured output
    - name: report_generator
      role: Report Generator
      job: "Generate a structured final report"
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.2
      parser:
        name: ReportFormat
        fields:
          - name: summary
            type: str
            description: "Executive summary"
          - name: findings
            type: array
            items:
              type: str
            description: "Key findings list"
          - name: recommendations
            type: array
            items:
              type: str
            description: "Recommended actions"
        
  workflow:
    start: input_validator
    edges:
      - from: input_validator
        to: [data_processor]
      - from: data_processor
        to: [report_generator]
      - from: report_generator
        to: [end]
    end: [report_generator]
"""


# Custom router function for the complex workflow
def research_router(
    memory: BaseMemory,
) -> Literal['math_specialist', 'text_specialist', 'final_summarizer']:
    """
    Custom router that decides the next step based on memory content.

    This is a simple example - in practice, this could be more sophisticated,
    potentially using LLM-based decision making.
    """
    # Get the latest content from memory
    memory_content = memory.get()
    latest_message = memory_content[-1] if memory_content else {}

    # Simple text-based routing logic
    content_text = str(latest_message).lower()

    if any(
        keyword in content_text
        for keyword in ['calculate', 'math', 'number', 'compute']
    ):
        return 'math_specialist'
    elif any(
        keyword in content_text for keyword in ['text', 'analyze', 'process', 'parse']
    ):
        return 'text_specialist'
    else:
        return 'final_summarizer'


# Custom router function for the mixed nodes workflow
def dispatch_router(
    memory: BaseMemory,
) -> Literal['math_agent', 'text_agent', 'final_summarizer']:
    """
    Custom router for the mixed nodes workflow that decides the next step.
    """
    memory_content = memory.get()
    latest_message = memory_content[-1] if memory_content else {}
    content_text = str(latest_message).lower()

    if any(
        keyword in content_text
        for keyword in ['calculate', 'math', 'number', 'compute', 'add', 'multiply']
    ):
        return 'math_agent'
    elif any(
        keyword in content_text
        for keyword in ['text', 'analyze', 'process', 'parse', 'word']
    ):
        return 'text_agent'
    else:
        return 'final_summarizer'


async def create_example_tools() -> Dict[str, Tool]:
    """Create example tools for the workflow."""

    # Calculator tool
    async def calculate(operation: str, x: float, y: float) -> str:
        operations = {
            'add': lambda: x + y,
            'subtract': lambda: x - y,
            'multiply': lambda: x * y,
            'divide': lambda: x / y if y != 0 else 'Cannot divide by zero',
        }
        if operation not in operations:
            return f'Unknown operation: {operation}'
        result = operations[operation]()
        return f'Calculation result: {x} {operation} {y} = {result}'

    calculator_tool = Tool(
        name='calculator',
        description='Perform basic mathematical calculations',
        function=calculate,
        parameters={
            'operation': {
                'type': 'string',
                'description': 'The operation to perform (add, subtract, multiply, divide)',
            },
            'x': {'type': 'number', 'description': 'First number'},
            'y': {'type': 'number', 'description': 'Second number'},
        },
    )

    # Text processor tool
    async def process_text(text: str, operation: str = 'analyze') -> str:
        operations = {
            'analyze': lambda t: f'Text analysis: {len(t)} characters, {len(t.split())} words',
            'uppercase': lambda t: t.upper(),
            'lowercase': lambda t: t.lower(),
            'word_count': lambda t: f'Word count: {len(t.split())}',
        }

        if operation not in operations:
            return f'Unknown text operation: {operation}'

        result = operations[operation](text)
        return f'Text processing result: {result}'

    text_processor_tool = Tool(
        name='text_processor',
        description='Process and analyze text content',
        function=process_text,
        parameters={
            'text': {'type': 'string', 'description': 'Text to process'},
            'operation': {
                'type': 'string',
                'description': 'Operation to perform (analyze, uppercase, lowercase, word_count)',
                'required': False,
            },
        },
    )

    return {
        'calculator': calculator_tool,
        'text_processor': text_processor_tool,
    }


async def create_example_functions() -> Dict[str, Callable]:
    """Create example functions for function nodes."""
    from typing import List, Any

    async def validate_data(
        inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        """Validates and cleans input data."""
        text = str(inputs[-1]) if inputs else ''

        cleaned = ' '.join(text.split())
        if not cleaned:
            return 'Error: Empty input data'

        validation_result = (
            f'✓ Data validated: {len(cleaned)} characters, {len(cleaned.split())} words'
        )
        return validation_result

    async def transform_data(
        inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        """Transforms data into a structured format."""
        text = str(inputs[-1]) if inputs else ''

        words = text.split()
        transformed = f'STRUCTURED DATA:\n- Word count: {len(words)}\n- Character count: {len(text)}\n- Content: {text[:100]}...'
        return transformed

    async def preprocess_input(
        inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        """Preprocesses input data before agent processing."""
        text = str(inputs[-1]) if inputs else ''

        normalized = text.strip().lower()
        preprocessed = f'[PREPROCESSED] {normalized}'
        return preprocessed

    async def aggregate_results(
        inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> str:
        """Aggregates results from multiple processing paths."""
        results = []
        for inp in inputs:
            if hasattr(inp, 'content'):
                results.append(str(inp.content))
            else:
                results.append(str(inp))

        aggregated = 'AGGREGATED RESULTS:\n' + '\n'.join(f'- {r}' for r in results)
        return aggregated

    return {
        'validate_data': validate_data,
        'transform_data': transform_data,
        'preprocess_input': preprocess_input,
        'aggregate_results': aggregate_results,
    }


async def run_simple_example():
    """Run the simple workflow example."""
    print('=' * 60)
    print('RUNNING SIMPLE WORKFLOW EXAMPLE')
    print('=' * 60)

    # Create builder from YAML
    builder = AriumBuilder.from_yaml(yaml_str=SIMPLE_WORKFLOW_YAML)

    # Run the workflow
    result: List[MessageMemoryItem] = await builder.build_and_run(
        [
            UserMessage(
                'Machine learning is transforming healthcare by enabling predictive analytics, '
                'personalized treatment recommendations, and automated medical imaging analysis. '
                'However, challenges include data privacy concerns, the need for regulatory approval, '
                'and ensuring AI systems are transparent and unbiased in their decision-making.',
            )
        ]
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result):
        print(f'{i+1}. {message.result.content}')

    return result


async def run_complex_example():
    """Run the complex workflow example with tools and routing."""
    print('\n' + '=' * 60)
    print('RUNNING COMPLEX WORKFLOW EXAMPLE')
    print('=' * 60)

    # Create tools
    tools = await create_example_tools()

    # Create routers dictionary
    routers = {'research_router': research_router}

    # Create builder from YAML
    builder = AriumBuilder.from_yaml(
        yaml_str=COMPLEX_WORKFLOW_YAML, tool_registry=tools, routers=routers
    )

    # Test with mathematical content
    print('\nTesting with mathematical content:')
    result1 = await builder.build_and_run(
        ['Please calculate the sum of 25 and 17, then multiply the result by 3.']
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result1):
        print(f'{i+1}. {message.result.content}')

    # Reset and test with text content
    print('\nTesting with text content:')
    builder.reset()
    builder = AriumBuilder.from_yaml(
        yaml_str=COMPLEX_WORKFLOW_YAML, tool_registry=tools, routers=routers
    )

    result2 = await builder.build_and_run(
        [
            UserMessage(
                "Please analyze this text and process it: 'The quick brown fox jumps over the lazy dog.'"
            ),
            UserMessage(
                "This sentence contains every letter of the alphabet at least once.'"
            ),
        ]
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result2):
        print(f'{i+1}. {message.result.content}')

    return result1, result2


async def run_mixed_config_example():
    """Run the mixed configuration example showing different agent definition methods."""
    print('\n' + '=' * 60)
    print('RUNNING MIXED CONFIGURATION EXAMPLE')
    print('=' * 60)

    # Create builder from YAML (no tools needed for this example)
    builder = AriumBuilder.from_yaml(yaml_str=MIXED_CONFIG_YAML)

    # Run the workflow
    result = await builder.build_and_run(
        [
            UserMessage(
                'Please analyze this business report: Our Q3 revenue increased by 15% compared to Q2, '
                'driven primarily by strong performance in the software division. However, hardware sales '
                'declined by 8%. Customer satisfaction scores improved to 4.2/5.0. We recommend focusing '
                'on digital transformation initiatives and reconsidering the hardware product line.'
            ),
        ]
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result):
        print(f'{i+1}. {message.result.content}')

    return result


async def run_function_nodes_example():
    """Run the function nodes workflow example."""
    print('\n' + '=' * 60)
    print('RUNNING FUNCTION NODES WORKFLOW EXAMPLE')
    print('=' * 60)

    # Create function registry
    functions = await create_example_functions()

    # Create builder from YAML with function registry
    builder = AriumBuilder.from_yaml(
        yaml_str=FUNCTION_NODES_WORKFLOW_YAML, function_registry=functions
    )

    # Run the workflow
    result = await builder.build_and_run(
        [
            UserMessage(
                'Sample data for processing: Customer satisfaction scores show 85% positive feedback, '
                'with response times averaging 2.3 minutes. Revenue increased by 12% this quarter.'
            ),
        ]
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result):
        print(f'{i+1}. {message.result.content}')

    return result


async def run_mixed_nodes_example():
    """Run the mixed nodes workflow example with agents, function nodes, and routing."""
    print('\n' + '=' * 60)
    print('RUNNING MIXED NODES WORKFLOW EXAMPLE')
    print('=' * 60)

    # Create tools and functions
    tools = await create_example_tools()
    functions = await create_example_functions()
    routers = {'dispatch_router': dispatch_router}

    # Create builder from YAML
    builder = AriumBuilder.from_yaml(
        yaml_str=MIXED_NODES_WORKFLOW_YAML,
        tool_registry=tools,
        function_registry=functions,
        routers=routers,
    )

    # Test with mathematical content
    print('\nTesting with mathematical content:')
    result1 = await builder.build_and_run(
        ['Please calculate the sum of 15 and 27, then multiply by 2.']
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result1):
        print(f'{i+1}. {message.result.content}')

    # Reset and test with text content
    print('\nTesting with text content:')
    builder.reset()
    builder = AriumBuilder.from_yaml(
        yaml_str=MIXED_NODES_WORKFLOW_YAML,
        tool_registry=tools,
        function_registry=functions,
        routers=routers,
    )

    result2 = await builder.build_and_run(
        [
            UserMessage(
                'Please analyze and process this text: Machine learning algorithms '
                'are transforming how we process and understand data.'
            ),
        ]
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result2):
        print(f'{i+1}. {message.result.content}')

    return result1, result2


async def run_prebuilt_agents_example():
    """Run example using pre-built agents with YAML workflow."""
    print('\n' + '=' * 60)
    print('RUNNING PRE-BUILT AGENTS EXAMPLE')
    print('=' * 60)

    # Build agents separately using AgentBuilder
    from flo_ai.builder.agent_builder import AgentBuilder
    from flo_ai.models.base_agent import ReasoningPattern

    llm = OpenAI(model='gpt-4o-mini')

    # Agent 1: Built from YAML string
    content_analyst_yaml = """
    agent:
      name: content_analyst
      role: Content Analyst
      job: >
        You are a content analyst. Analyze the input and extract:
        1. Main themes and topics
        2. Key insights and findings
        3. Important facts and figures
        
        Provide a structured analysis for the next agent.
      model:
        provider: openai
        name: gpt-4o-mini
      settings:
        temperature: 0.3
        reasoning_pattern: COT
    """

    content_analyst = AgentBuilder.from_yaml(yaml_str=content_analyst_yaml).build()

    # Agent 2: Built programmatically
    summarizer = (
        AgentBuilder()
        .with_name('summarizer')
        .with_role('Executive Summarizer')
        .with_prompt(
            'Create a concise executive summary from the content analysis. Focus on actionable insights and key recommendations.'
        )
        .with_llm(llm)
        .with_reasoning(ReasoningPattern.DIRECT)
        .build()
    )

    # Dictionary of pre-built agents
    prebuilt_agents = {'content_analyst': content_analyst, 'summarizer': summarizer}

    # Clean workflow YAML that references the pre-built agents
    workflow_yaml = """
    metadata:
      name: prebuilt-agents-workflow
      version: 1.0.0
      description: "Workflow using pre-built agents and inline definitions"
    
    arium:
      agents:
        # Reference pre-built agents (must exist in agents parameter)
        - name: content_analyst
        - name: summarizer
        
        # Mix with direct configuration
        - name: quality_checker
          role: Quality Assurance
          job: "Review the analysis and summary for completeness and accuracy"
          model:
            provider: openai
            name: gpt-4o-mini
          settings:
            temperature: 0.1
            max_retries: 2
            
      workflow:
        start: content_analyst
        edges:
          - from: content_analyst
            to: [summarizer]
          - from: summarizer
            to: [quality_checker]
          - from: quality_checker
            to: [end]
        end: [quality_checker]
    """

    # Create builder with pre-built agents
    builder = AriumBuilder.from_yaml(
        yaml_str=workflow_yaml,
        agents=prebuilt_agents,  # Pass the pre-built agents
    )

    # Run the workflow
    result = await builder.build_and_run(
        [
            'The global renewable energy market reached $1.1 trillion in 2023, representing a 15% '
            'increase from the previous year. Solar energy dominated with 45% market share, followed '
            'by wind energy at 35%. Government incentives in Europe and Asia drove significant growth, '
            'while corporate sustainability commitments increased private sector investment. However, '
            'supply chain challenges and raw material costs remain key obstacles. Industry experts '
            'predict continued expansion, with the market expected to reach $1.8 trillion by 2030.'
        ]
    )

    print('Result:')
    for i, message in enumerate[MessageMemoryItem](result):
        print(f'{i+1}. {message.result.content}')

    return result


async def main():
    """Main function to run all examples."""
    try:
        # Run simple example
        await run_simple_example()

        # Run complex example
        await run_complex_example()

        # Run mixed configuration example
        await run_mixed_config_example()

        # Run function nodes example
        await run_function_nodes_example()

        # Run mixed nodes example
        await run_mixed_nodes_example()

        # Run pre-built agents example
        await run_prebuilt_agents_example()

        print('\n' + '=' * 60)
        print('ALL EXAMPLES COMPLETED SUCCESSFULLY!')
        print('=' * 60)
        print('\n📋 Examples demonstrated:')
        print('   • Simple linear workflow with direct agent configuration')
        print('   • Complex workflow with tools and conditional routing')
        print('   • Mixed configuration approaches')
        print('   • Function nodes workflow (NEW!)')
        print('   • Mixed nodes workflow with agents and function nodes (NEW!)')
        print('   • Pre-built agents with YAML workflow')

    except Exception as e:
        print(f'Error running examples: {e}')
        raise


if __name__ == '__main__':
    asyncio.run(main())
