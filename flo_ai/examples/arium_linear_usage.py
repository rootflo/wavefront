import asyncio
from flo_ai.arium.builder import AriumBuilder
from flo_ai.models.agent import Agent
from flo_ai.llm.openai_llm import OpenAI


async def simple_example():
    """
    Simple example: 2 agents connected directly together
    Agent 1 (Greeter) -> Agent 2 (Responder)
    """
    llm = OpenAI(model='gpt-4o-mini', temperature=0.7)

    # Agent 1: Greeter
    greeter = Agent(
        name='greeter',
        system_prompt='You are a friendly greeter. Say hello and introduce the topic to the next agent.',
        llm=llm,
    )

    # Agent 2: Responder
    responder = Agent(
        name='responder',
        system_prompt='You are a helpful responder. Provide a thoughtful response to what the greeter shared.',
        llm=llm,
    )

    # Connect agents directly: greeter -> responder
    result = await (
        AriumBuilder()
        .add_agent(greeter)
        .add_agent(responder)
        .start_with(greeter)
        .connect(greeter, responder)  # Direct connection
        .end_with(responder)
        .build_and_run(["Hello, I'd like to learn about Python programming!"])
    )

    print('Simple Example Result:')
    print(result)
    return result


async def main():
    """
    Example showing how to create 2 simple agents connected directly together
    using the AriumBuilder.
    """

    # Create LLM instance
    llm = OpenAI(model='gpt-4o-mini', temperature=0.7)

    # Create first agent - Content Analyst
    content_analyst = Agent(
        name='content_analyst',
        system_prompt="""You are a content analyst. When you receive input, analyze it and provide:
        1. A brief summary of the content
        2. The main topics covered
        3. Any insights or observations
        
        Pass your analysis to the next agent for final processing.""",
        llm=llm,
        role='Content Analyst',
    )

    # Create second agent - Summary Generator
    summary_generator = Agent(
        name='summary_generator',
        system_prompt="""You are a summary generator. You receive analysis from the content analyst.
        Your job is to create a concise, well-structured final summary that includes:
        1. Key takeaways
        2. Actionable insights
        3. A clear conclusion
        
        Make your response clear and professional.""",
        llm=llm,
        role='Summary Generator',
    )

    # Create Arium workflow using AriumBuilder
    print('Building Arium workflow...')

    result = await (
        AriumBuilder()
        .add_agents([content_analyst, summary_generator])
        .start_with(content_analyst)
        .connect(content_analyst, summary_generator)  # Direct connection
        .end_with(summary_generator)
        .build_and_run(
            [
                'Machine learning is revolutionizing various industries. '
                'From healthcare to finance, AI systems are being deployed '
                'to automate processes, improve decision-making, and enhance '
                'customer experiences. However, challenges remain around '
                'data privacy, algorithmic bias, and the need for skilled '
                'professionals to manage these systems effectively.'
            ]
        )
    )

    print('\n' + '=' * 50)
    print('ARIUM WORKFLOW RESULT:')
    print('=' * 50)
    print(result)


if __name__ == '__main__':
    print('Running simple example first...')
    asyncio.run(simple_example())

    print('\n' + '=' * 80)
    print('Now running detailed example...')
    asyncio.run(main())
