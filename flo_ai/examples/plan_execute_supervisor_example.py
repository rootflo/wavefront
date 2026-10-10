"""
Plan-and-execute, and a supervisor that delegates to other agents.

This example shows:
1. An agent that plans its work before carrying it out
   (ReasoningPattern.PLAN_EXECUTE)
2. A supervisor whose tools are other agents (Agent.as_tool)

Requires OPENAI_API_KEY to be set.
"""

import asyncio

from flo_ai.agent import AgentBuilder, ReasoningPattern
from flo_ai.llm import OpenAI
from flo_ai.tool import parallel_agents_tool
from flo_ai.tool.flo_tool import flo_tool

POPULATIONS = {'france': 68_000_000, 'germany': 84_000_000, 'spain': 48_000_000}


@flo_tool(
    description='Look up the population of a country',
    parameter_descriptions={'country': 'Country name'},
)
async def get_population(country: str) -> str:
    population = POPULATIONS.get(country.lower())
    if population is None:
        return f'No population data for {country}'
    return f'{country}: {population}'


def print_plan(agent) -> None:
    print(f'\nPlan kept by {agent.name}:')
    print(agent.plan.render())


async def planning_agent(llm) -> None:
    """One agent, ordinary tools, working from a plan."""
    agent = (
        AgentBuilder()
        .with_name('analyst')
        .with_prompt('You answer questions about countries using your tools.')
        .with_llm(llm)
        .with_tools([get_population.tool])
        .with_reasoning(ReasoningPattern.PLAN_EXECUTE)
        .with_max_tool_calls(10)
        .build()
    )

    history = await agent.run(
        'Which of France, Germany and Spain has the largest population, '
        'and what is the combined total?'
    )

    print_plan(agent)
    print(f'\nAnswer: {history[-1].content}')


async def supervisor(llm) -> None:
    """A supervisor whose tools are other agents."""
    researcher = (
        AgentBuilder()
        .with_name('researcher')
        .with_prompt('You look up facts with your tools and report them plainly.')
        .with_llm(llm)
        .with_tools([get_population.tool])
        .build()
    )
    writer = (
        AgentBuilder()
        .with_name('writer')
        .with_prompt('You turn the facts you are given into two clear sentences.')
        .with_llm(llm)
        .build()
    )

    # Each worker becomes a tool taking one `task` argument. The worker sees
    # only that task; the supervisor sees only the worker's final answer.
    lead = (
        AgentBuilder()
        .with_name('lead')
        .with_prompt(
            'You coordinate specialists. Delegate the work to them and combine '
            'their results into the final answer.'
        )
        .with_llm(llm)
        .with_tools(
            [
                researcher.as_tool('Looks up country facts such as population'),
                writer.as_tool('Writes a short summary from facts you supply'),
                # Lets the lead hand out independent tasks in one call, e.g.
                # one lookup per country, and have them run together.
                parallel_agents_tool([researcher, writer]),
            ]
        )
        .with_reasoning(ReasoningPattern.PLAN_EXECUTE)
        .with_max_tool_calls(10)
        .build()
    )

    history = await lead.run(
        'Write a short comparison of the populations of France and Germany.'
    )

    print_plan(lead)
    print(f'\nAnswer: {history[-1].content}')


async def main() -> None:
    llm = OpenAI(model='gpt-4o-mini')

    print('=== Planning agent ===')
    await planning_agent(llm)

    print('\n=== Supervisor ===')
    await supervisor(llm)


if __name__ == '__main__':
    asyncio.run(main())
