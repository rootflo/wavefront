#!/usr/bin/env python3
"""
Example script demonstrating the graph visualization feature in BaseArium.
This script creates a simple workflow with agents and tools, then generates a PNG visualization.
"""

from flo_ai.arium.base import BaseArium
from flo_ai.models.agent import Agent
from flo_ai.tool.flo_tool import flo_tool
from flo_ai.llm.openai_llm import OpenAI
from typing import Literal


# Create a simple validation tool using the @flo_tool decorator
@flo_tool(
    name='validation_tool',
    description='Validates input data and returns validation status',
    parameter_descriptions={
        'data': 'The data to validate',
        'strict': 'Whether to use strict validation rules',
    },
)
async def validate_data(data: str, strict: bool = False) -> str:
    """Validate the input data according to specified rules."""
    if not data:
        return 'invalid: empty data'

    if strict and len(data) < 10:
        return 'invalid: data too short for strict validation'

    return 'valid: data passed validation'


# Create mock agents for demonstration
def create_sample_agents():
    """Create sample agents for the demonstration"""
    # Note: This would normally require a valid OpenAI API key
    # For demonstration purposes, we'll use a mock LLM
    try:
        llm = OpenAI(model='gpt-4')
    except Exception:
        # If OpenAI is not available, create a mock LLM
        class MockLLM:
            def __init__(self, model):
                self.model = model

        llm = MockLLM('gpt-4')

    input_processor = Agent(
        name='input_processor',
        system_prompt='Process incoming requests',
        llm=llm,
        role='Input Processor',
    )

    analyzer = Agent(
        name='analyzer',
        system_prompt='Analyze processed data',
        llm=llm,
        role='Data Analyzer',
    )

    decision_maker = Agent(
        name='decision_maker',
        system_prompt='Make decisions based on analysis',
        llm=llm,
        role='Decision Maker',
    )

    output_formatter = Agent(
        name='output_formatter',
        system_prompt='Format final output',
        llm=llm,
        role='Output Formatter',
    )

    return input_processor, analyzer, decision_maker, output_formatter


# Router function for demonstration
def analysis_router(
    analysis_result: str,
) -> Literal['decision_maker', 'output_formatter']:
    """Route based on analysis result"""
    if 'complex' in analysis_result.lower():
        return 'decision_maker'
    else:
        return 'output_formatter'


def main():
    """Create a sample workflow and generate visualization"""

    # Create the BaseArium instance
    arium = BaseArium()

    # Create sample agents and tools
    input_processor, analyzer, decision_maker, output_formatter = create_sample_agents()

    # Get the tool from the decorated function
    validation_tool = validate_data.tool

    # Add nodes to the arium
    arium.add_nodes(
        [input_processor, validation_tool, analyzer, decision_maker, output_formatter]
    )

    # Set up the workflow
    # Start with input processor
    arium.start_at(input_processor)

    # Input processor -> Validation tool
    arium.add_edge('input_processor', ['validation_tool'])

    # Validation tool -> Analyzer
    arium.add_edge('validation_tool', ['analyzer'])

    # Analyzer -> Decision maker OR Output formatter (with router)
    arium.add_edge(
        'analyzer', ['decision_maker', 'output_formatter'], router=analysis_router
    )

    # Decision maker -> Output formatter
    arium.add_edge('decision_maker', ['output_formatter'])

    # Output formatter -> End
    arium.add_end_to(output_formatter)

    # Validate the graph
    try:
        arium.validate_graph()
        print('✅ Graph validation successful!')
    except ValueError as e:
        print(f'❌ Graph validation failed: {e}')
        return

    # Generate visualization
    print('🎨 Generating graph visualization...')

    # Generate with default settings
    arium.visualize_graph('workflow_graph.png')

    # Generate with custom settings
    arium.visualize_graph(
        output_path='custom_workflow_graph.png',
        figsize=(14, 10),
        node_size=4000,
        font_size=12,
        dpi=400,
    )

    print('✅ Graph visualization completed!')
    print('📁 Check the following files:')
    print('   - workflow_graph.png (default settings)')
    print('   - custom_workflow_graph.png (custom settings)')


if __name__ == '__main__':
    main()
