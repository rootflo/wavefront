"""
Examples demonstrating how to use the AriumBuilder pattern for creating and running Arium workflows.
"""

from typing import Literal
from flo_ai.arium import AriumBuilder, create_arium
from flo_ai.llm import OpenAI
from flo_ai.models import TextMessageContent, UserMessage
from flo_ai.models.agent import Agent
from flo_ai.tool import flo_tool
from flo_ai.tool.base_tool import Tool
from flo_ai.arium.memory import MessageMemory


@flo_tool(
    description='Calculate mathematical expressions',
    parameter_descriptions={
        'result': 'The result to print',
    },
)
async def print_result(result: str) -> str:
    print(f'Result: {result}')
    return result


# Example 1: Simple Linear Workflow
async def example_linear_workflow():
    """Example of a simple linear workflow: Agent -> Tool -> Agent"""

    # Create some example agents and tools (these would be your actual implementations)
    analyzer_agent = Agent(
        name='analyzer',
        system_prompt='Analyze the input',
        llm=OpenAI(model='gpt-4o-mini'),
    )
    summarizer_agent = Agent(
        name='summarizer',
        system_prompt='Summarize the results',
        llm=OpenAI(model='gpt-4o-mini'),
    )

    # Build and run the workflow
    result = await (
        AriumBuilder()
        .add_agent(analyzer_agent)
        .add_tool(print_result.tool)
        .add_agent(summarizer_agent)
        .start_with(analyzer_agent)
        .connect(analyzer_agent, print_result.tool)
        .connect(print_result.tool, summarizer_agent)
        .end_with(summarizer_agent)
        .build_and_run([UserMessage(TextMessageContent(text='Analyze this text'))])
    )

    return result


# Example 2: Branching Workflow with Router
async def example_branching_workflow():
    """Example of a branching workflow with conditional routing"""

    # Create agents and tools
    classifier_agent = Agent(name='classifier', prompt='Classify the input type')
    text_processor = Tool(name='text_processor')
    image_processor = Tool(name='image_processor')
    final_agent = Agent(name='final', prompt='Provide final response')

    # Router function for conditional branching
    def content_router(memory) -> Literal['text_processor', 'image_processor']:
        # Simple example logic (in real use, this would analyze the memory)
        last_message = memory[-1]['content']
        if 'image' in last_message.lower():
            return 'image_processor'
        return 'text_processor'

    # Build the workflow
    result = await (
        AriumBuilder()
        .add_agent(classifier_agent)
        .add_tool(text_processor)
        .add_tool(image_processor)
        .add_agent(final_agent)
        .start_with(classifier_agent)
        .add_edge(classifier_agent, [text_processor, image_processor], content_router)
        .connect(text_processor, final_agent)
        .connect(image_processor, final_agent)
        .end_with(final_agent)
        .build_and_run(['Process this content'])
    )

    return result


# Example 3: Complex Multi-Agent Workflow
async def example_complex_workflow():
    """Example of a more complex workflow with multiple agents and tools"""

    # Create multiple agents and tools
    input_agent = Agent(name='input_handler', prompt='Handle initial input')
    researcher_agent = Agent(name='researcher', prompt='Research the topic')
    analyzer_agent = Agent(name='analyzer', prompt='Analyze findings')
    writer_agent = Agent(name='writer', prompt='Write the final report')

    search_tool = Tool(name='search_tool')
    data_tool = Tool(name='data_processor')

    # Router for deciding next step after analysis
    def analysis_router(memory) -> Literal['writer', 'researcher']:
        # Example logic: if we need more research, go back to researcher
        # otherwise go to writer
        return 'writer'  # Simplified for example

    # Build complex workflow
    arium = (
        AriumBuilder()
        .add_agents([input_agent, researcher_agent, analyzer_agent, writer_agent])
        .add_tools([search_tool, data_tool])
        .with_memory(MessageMemory())
        .start_with(input_agent)
        .connect(input_agent, researcher_agent)
        .connect(researcher_agent, search_tool)
        .connect(search_tool, data_tool)
        .connect(data_tool, analyzer_agent)
        .add_edge(analyzer_agent, [writer_agent, researcher_agent], analysis_router)
        .end_with(writer_agent)
        .build()
    )

    # You can also visualize the workflow
    arium.visualize_graph(
        output_path='complex_workflow.png', graph_title='Complex Multi-Agent Workflow'
    )

    # Run the workflow
    result = await arium.run(['Research and write a report on AI trends'])
    return result


# Example 4: Using the convenience function
async def example_convenience_function():
    """Example using the create_arium convenience function"""

    agent1 = Agent(
        name='agent1', system_prompt='First agent', llm=OpenAI(model='gpt-4o-mini')
    )
    agent2 = Agent(
        name='agent2', system_prompt='Second agent', llm=OpenAI(model='gpt-4o-mini')
    )

    # Fix: Use proper InputMessage format for consistency
    result = await (
        create_arium()
        .add_agent(agent1)
        .add_agent(agent2)
        .start_with(agent1)
        .connect(agent1, agent2)
        .end_with(agent2)
        .build_and_run([UserMessage(TextMessageContent(text='Hello'))])
    )

    return result


# Example 5: Building and reusing an Arium
async def example_build_and_reuse():
    """Example of building an Arium once and reusing it"""

    agent = Agent(name='echo_agent', prompt='Echo the input')

    # Build the Arium
    arium = AriumBuilder().add_agent(agent).start_with(agent).end_with(agent).build()

    # Run it multiple times with different inputs
    result1 = await arium.run(['First input'])
    result2 = await arium.run(['Second input'])

    return result1, result2


if __name__ == '__main__':
    import asyncio

    # Run the examples
    async def main():
        print('Running AriumBuilder examples...')

        # You can uncomment and run these examples
        # result1 = await example_linear_workflow()
        # result2 = await example_branching_workflow()
        # result3 = await example_complex_workflow()
        # result4 = await example_convenience_function()
        # result5 = await example_build_and_reuse()
        print('Examples completed!')

    asyncio.run(main())
