"""
Expose an agent as a tool, so another agent can delegate work to it.

This is how a supervisor is built: the supervising agent's tool loop calls the
worker, the worker's answer comes back as the tool result, and the supervisor
decides what to do next. No workflow edges or routers are involved.
"""

import asyncio
import json
import re
import weakref
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from flo_ai.models.agent_error import AgentError
from flo_ai.tool.base_tool import Tool

if TYPE_CHECKING:  # agent imports the tool package, so avoid a circular import
    from flo_ai.agent.agent import Agent


PARALLEL_TOOL_NAME = 'delegate_parallel'

# An agent holds a single conversation, so two tasks handed to the same agent
# at once would write over each other. Tasks for one agent queue here; tasks
# for different agents run side by side.
_delegation_locks: 'weakref.WeakKeyDictionary[Agent, asyncio.Lock]' = (
    weakref.WeakKeyDictionary()
)


def _tool_name(agent: 'Agent') -> str:
    """The agent's name with characters providers reject in function names replaced"""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', agent.name)


def _describe(agent: 'Agent', description: Optional[str] = None) -> str:
    return description or agent.role or f'Delegate a task to the {agent.name} agent'


async def _run_task(agent: 'Agent', task: str) -> str:
    """Run ``task`` on ``agent`` from an empty conversation and return its answer"""
    lock = _delegation_locks.setdefault(agent, asyncio.Lock())
    async with lock:
        agent.clear_history()
        try:
            history = await agent.run(task)
        except AgentError as e:
            # An error that declares itself final (a guardrail block) is a
            # decision about the whole request, not something to plan around.
            if getattr(e, 'retryable', True) is False:
                raise
            # Otherwise the caller can re-plan around a worker that failed, so
            # it gets the failure as a result instead of having its run aborted.
            return f'{agent.name} failed: {e}'

        if not history:
            return ''
        content = history[-1].content
        return str(getattr(content, 'text', content))


def agent_as_tool(
    agent: 'Agent',
    description: Optional[str] = None,
    name: Optional[str] = None,
) -> Tool:
    """Wrap ``agent`` in a tool that takes a single ``task`` string.

    Args:
        agent: The agent to delegate to.
        description: Tells the calling model when to use this agent. Defaults
            to the agent's role.
        name: Tool name. Defaults to the agent's name, with characters that
            providers reject in function names replaced by underscores.

    Each call starts the agent from an empty conversation: it sees only the
    task it is given, and the caller sees only its final answer.
    """

    async def _delegate(task: str) -> str:
        return await _run_task(agent, task)

    tool = Tool(
        name=name or _tool_name(agent),
        description=_describe(agent, description),
        function=_delegate,
        parameters={
            'task': {
                'type': 'string',
                'description': (
                    'The task to perform. Include all the context needed: '
                    'this agent cannot see your conversation.'
                ),
            }
        },
    )
    tool.agents = [agent]
    return tool


def parallel_agents_tool(
    agents: List['Agent'],
    descriptions: Optional[Dict[str, str]] = None,
    name: str = PARALLEL_TOOL_NAME,
) -> Tool:
    """Create a tool that hands several tasks to ``agents`` at the same time.

    Give it to a supervisor alongside the agents' own tools. The supervisor
    then makes one call with a list of ``{agent, task}`` pairs, the tasks run
    concurrently, and all the answers come back together.

    Args:
        agents: The agents that can be delegated to.
        descriptions: Optional description per agent name, shown to the calling
            model. Defaults to each agent's role.
        name: Tool name.

    Tasks for different agents run concurrently. Two tasks for the same agent
    in one call run one after the other, since an agent holds one conversation.
    """
    descriptions = descriptions or {}
    by_name = {_tool_name(agent): agent for agent in agents}
    agent_list = '\n'.join(
        f'- {tool_name}: {_describe(agent, descriptions.get(agent.name))}'
        for tool_name, agent in by_name.items()
    )

    async def _delegate_parallel(tasks: Any) -> str:
        # A malformed call is the model's mistake to correct, so it gets the
        # reason back as a result instead of failing the supervisor's run.
        if isinstance(tasks, str):
            try:
                tasks = json.loads(tasks)
            except json.JSONDecodeError as e:
                return f'No tasks were run: tasks is not valid JSON: {e}'
        if not isinstance(tasks, list) or not tasks:
            return 'No tasks were run: tasks must be a non-empty list'

        jobs = []
        for index, item in enumerate(tasks, 1):
            agent_name = item.get('agent') if isinstance(item, dict) else None
            task = item.get('task') if isinstance(item, dict) else None
            if agent_name not in by_name:
                return (
                    f"No tasks were run: task {index} names unknown agent '{agent_name}' "
                    f"(use one of: {', '.join(by_name)})"
                )
            if not task:
                return f'No tasks were run: task {index} has no task text'
            jobs.append((agent_name, str(task)))

        results = await asyncio.gather(
            *(_run_task(by_name[agent_name], task) for agent_name, task in jobs),
            return_exceptions=True,
        )
        # Anything a worker raised instead of returning ends the call: workers
        # report ordinary failures as text, so what is left is final.
        for result in results:
            if isinstance(result, BaseException):
                raise result

        return '\n\n'.join(
            f'[{index}] {agent_name}: {task}\n{result}'
            for index, ((agent_name, task), result) in enumerate(zip(jobs, results), 1)
        )

    tool = Tool(
        name=name,
        description=(
            'Delegate several tasks at the same time and get all the results '
            'back together. Use it when the tasks do not depend on each '
            "other's results. Agents:\n" + agent_list
        ),
        function=_delegate_parallel,
        parameters={
            'tasks': {
                'type': 'array',
                'description': 'The tasks to run at the same time',
                'items': {
                    'type': 'object',
                    'properties': {
                        'agent': {
                            'type': 'string',
                            'enum': list(by_name),
                            'description': 'Which agent does the task',
                        },
                        'task': {
                            'type': 'string',
                            'description': (
                                'The task to perform. Include all the context '
                                'needed: the agent cannot see your conversation.'
                            ),
                        },
                    },
                    'required': ['agent', 'task'],
                },
            }
        },
    )
    tool.agents = list(agents)
    return tool
