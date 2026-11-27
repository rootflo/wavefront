"""Authorization hooks around an agent's tools.

When an agent is built, ``filter_capabilities`` decides which of its tools it
gets. Each tool it keeps is wrapped so that every call is checked with
``authorize_call`` first. Datasource and knowledge-base access by an agent goes
through tools, so it is covered by the same checks.

The principal is captured when the agent is built: an agent can outlive the
request that built it (a streamed response, say), and its tool calls still act
for that caller.
"""

from __future__ import annotations

import copy
import functools
from typing import Any, Callable, Mapping

from authz_module import Capability, Principal, ResourceRef, current_principal
from authz_module import hooks
from flo_ai.tool.base_tool import Tool

# Call arguments that name the resource a tool is about to touch.
RESOURCE_ARGUMENTS = (
    'datasource_id',
    'knowledge_base_id',
    'kb_id',
    'table_name',
    'connection_id',
    'service_id',
)


def _call_attributes(kwargs: Mapping[str, Any]) -> dict[str, str]:
    return {
        name: str(kwargs[name])
        for name in RESOURCE_ARGUMENTS
        if kwargs.get(name) is not None
    }


def guard_tool(
    tool: Tool,
    *,
    agent: ResourceRef,
    kind: str,
    principal: Principal | None,
) -> Tool:
    """A copy of ``tool`` whose every call is authorized first."""
    original = tool.function
    name = tool.name

    async def authorized_call(**kwargs):
        await hooks.ensure_call_allowed(
            agent,
            Capability(kind, name, _call_attributes(kwargs)),
            principal=principal,
        )
        return await original(**kwargs)

    guarded = copy.copy(tool)
    guarded.function = authorized_call
    return guarded


async def authorize_tools(
    agent: ResourceRef,
    tools: Mapping[str, Tool],
    kinds: Mapping[str, str],
) -> dict[str, Tool]:
    """The tools this agent may have, each guarded per call."""
    principal = current_principal()
    allowed = await hooks.filter_capabilities(
        agent,
        list(tools.items()),
        lambda item: Capability(kinds.get(item[0], 'tool'), item[0]),
        principal=principal,
    )
    return {
        name: guard_tool(
            tool, agent=agent, kind=kinds.get(name, 'tool'), principal=principal
        )
        for name, tool in allowed
    }


def guard_function_nodes(
    workflow: ResourceRef,
    registry: Mapping[str, Callable],
    kinds: Mapping[str, str],
) -> dict[str, Callable]:
    """A workflow's function-node registry with every call authorized first.

    Function nodes call registry functions directly rather than through a
    tool, so they get the same per-call check here. Arguments come in as
    ``variables``.
    """
    principal = current_principal()

    def guard(name: str, function: Callable) -> Callable:
        kind = kinds.get(name, 'tool')

        @functools.wraps(function)
        async def authorized_node(*args, **kwargs):
            variables = kwargs.get('variables') or {}
            await hooks.ensure_call_allowed(
                workflow,
                Capability(kind, name, _call_attributes(variables)),
                principal=principal,
            )
            return await function(*args, **kwargs)

        return authorized_node

    return {name: guard(name, function) for name, function in registry.items()}
