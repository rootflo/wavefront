"""
Examples demonstrating how to use the AriumBuilder pattern for creating and running Arium workflows.
"""

from typing import Literal
from flo_ai.arium import AriumBuilder, create_arium
from flo_ai.llm import OpenAI
from flo_ai.models import TextMessageContent, UserMessage
from flo_ai.models.agent import Agent
from flo_ai.arium.nodes import FunctionNode
from flo_ai.arium.memory import MessageMemory, MessageMemoryItem
from flo_ai.models import BaseMessage
from typing import List


async def print_result(result: str) -> str:
    print(f'Result: {result}')
    return result


# Example 1: Simple Linear Workflow
async def example_linear_workflow():
    """Example of a simple linear workflow: Agent -> FunctionNode -> Agent"""

    # Create some example agents and function nodes (these would be your actual implementations)
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
    processing_function_node = FunctionNode(
        name='processor', description='Process the input', function=print_result
    )

    # Build and run the workflow
    result = await (
        AriumBuilder()
        .add_agent(analyzer_agent)
        .add_function_node(processing_function_node)
        .add_agent(summarizer_agent)
        .start_with(analyzer_agent)
        .connect(analyzer_agent, processing_function_node)
        .connect(processing_function_node, summarizer_agent)
        .end_with(summarizer_agent)
        .build_and_run([UserMessage(TextMessageContent(text='Analyze this text'))])
    )

    return result


# Example 2: Branching Workflow with Router
async def example_branching_workflow():
    """Example of a branching workflow with conditional routing"""

    # Create agents and function nodes
    classifier_agent = Agent(name='classifier', prompt='Classify the input type')
    text_processor_node = FunctionNode(
        name='text_processor', description='Process text', function=lambda x: x
    )
    image_processor_node = FunctionNode(
        name='image_processor', description='Process image', function=lambda x: x
    )
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
        .add_agent(final_agent)
        .add_function_node(
            FunctionNode(
                name='text_processor', description='Process text', function=lambda x: x
            )
        )
        .add_function_node(
            FunctionNode(
                name='image_processor',
                description='Process image',
                function=lambda x: x,
            )
        )
        .start_with(classifier_agent)
        .add_edge(
            classifier_agent,
            [text_processor_node, image_processor_node],
            content_router,
        )
        .connect(text_processor_node, final_agent)
        .connect(image_processor_node, final_agent)
        .end_with(final_agent)
        .build_and_run(['Process this content'])
    )
    return result


# Example 3: Complex Multi-Agent Workflow
async def example_complex_workflow():
    """Example of a more complex workflow with multiple agents and function nodes"""

    # Create multiple agents and function nodes
    input_agent = Agent(name='input_handler', prompt='Handle initial input')
    researcher_agent = Agent(name='researcher', prompt='Research the topic')
    analyzer_agent = Agent(name='analyzer', prompt='Analyze findings')
    writer_agent = Agent(name='writer', prompt='Write the final report')

    search_function_node = FunctionNode(
        name='search_function', description='Search the web', function=lambda x: x
    )
    data_function_node = FunctionNode(
        name='data_function', description='Process the data', function=lambda x: x
    )

    # Router for deciding next step after analysis
    def analysis_router(memory) -> Literal['writer', 'researcher']:
        # Example logic: if we need more research, go back to researcher
        # otherwise go to writer
        return 'writer'  # Simplified for example

    # Build complex workflow
    arium = (
        AriumBuilder()
        .add_agents([input_agent, researcher_agent, analyzer_agent, writer_agent])
        .add_function_nodes([search_function_node, data_function_node])
        .with_memory(MessageMemory())
        .start_with(input_agent)
        .connect(input_agent, researcher_agent)
        .connect(researcher_agent, search_function_node)
        .connect(search_function_node, data_function_node)
        .connect(data_function_node, analyzer_agent)
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


# Example 6: Four FunctionNodes with input filtering (no agents)
async def example_function_nodes_with_filters():
    """Workflow of only FunctionNodes; each uses input_filter to read from specific nodes."""

    # Define simple functions as nodes
    async def pass_through(inputs: List[BaseMessage] | str, variables=None, **kwargs):
        return inputs[-1].content

    async def capitalize_last(
        inputs: List[BaseMessage] | str, variables=None, **kwargs
    ):
        return str(inputs[-1].content).capitalize()

    async def uppercase_all(inputs: List[BaseMessage] | str, variables=None, **kwargs):
        return ' '.join([str(x.content).upper() for x in inputs])

    async def summarize(inputs: List[BaseMessage] | str, variables=None, **kwargs):
        return f"count={len(inputs or [])} last={(str(inputs[-1].content) if inputs else '')}"

    # Create four FunctionNodes with input filters
    t1 = FunctionNode(
        name='function1',
        description='reads initial inputs',
        function=pass_through,
        input_filter=['input'],
    )
    t2 = FunctionNode(
        name='function2',
        description='reads function1 only',
        function=capitalize_last,
        input_filter=['function1'],
    )
    t3 = FunctionNode(
        name='function3',
        description='reads function2 only',
        function=uppercase_all,
        input_filter=['function2'],
    )
    t4 = FunctionNode(
        name='function4',
        description='reads function1 & function3',
        function=summarize,
        input_filter=['function1', 'function3'],
    )

    # Build and run: function1 -> function2 -> function3 -> function4
    state = 1

    def router(memory: MessageMemory) -> Literal['function2', 'function4']:
        nonlocal state
        if state == 1:
            state = 2
            return 'function2'
        else:
            state = 1
            return 'function4'

    result = await (
        AriumBuilder()
        .with_memory(MessageMemory())
        .add_function_nodes([t1, t2, t3, t4])
        .start_with(t1)
        .add_edge(t1, [t2, t4], router=router)
        .connect(t2, t3)
        .connect(t3, t1)
        .end_with(t4)
        .build_and_run(['hello world'])
    )

    return result


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
        result6: List[MessageMemoryItem] = await example_function_nodes_with_filters()

        print(result6[-1].result.content)

        print('Examples completed!')

    asyncio.run(main())
