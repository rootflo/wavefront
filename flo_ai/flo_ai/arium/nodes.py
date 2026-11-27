from typing import List, Any, Dict, Optional, TYPE_CHECKING, Callable
from flo_ai.utils.logger import logger
from flo_ai.agent.base_agent import BaseAgent
from flo_ai.models import BaseMessage, UserMessage
from flo_ai.arium.protocols import ExecutableNode
import asyncio


if TYPE_CHECKING:  # need to have an optional import else will get circular dependency error as arium also has AriumNode reference
    from flo_ai.arium.arium import Arium
    from flo_ai.arium.base import AriumNodeType


class AriumNode:
    """
    Wrapper to use an Arium as a node in another Arium workflow.
    """

    def __init__(
        self,
        name: str,
        arium: 'Arium',
        inherit_variables: bool = True,
        input_filter: Optional[List[str]] = None,
    ):
        """
        Args:
            name: Name for this node in the parent workflow
            arium: The Arium workflow to execute
            inherit_variables: Whether to pass parent variables to sub-workflow
        """
        self.name = name
        self.arium = arium
        self.inherit_variables = inherit_variables
        self.input_filter: Optional[List[str]] = input_filter

    async def run(
        self, inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Any:
        """Execute the nested Arium workflow with isolated memory"""

        # Handle variable inheritance
        execution_variables = (
            (variables or {}).copy() if (self.inherit_variables and variables) else {}
        )

        # Execute the nested Arium with isolated memory
        # These inputs are this parent's node outputs, so the sub-workflow keeps
        # the producer already recorded on them rather than resetting it.
        result = await self.arium.run(
            inputs=inputs,
            variables=execution_variables,
            forwarded_from_parent=True,
        )
        return result


def _reachable_agents(node: Any) -> List[BaseAgent]:
    """Every agent a run of `node` can reach, through nested workflows too."""
    if isinstance(node, BaseAgent):
        return [node]
    if isinstance(node, AriumNode):
        children = list(node.arium.nodes.values())
    elif isinstance(node, ForEachNode):
        children = [node.execute_node]
    else:
        return []

    # Keyed by id so an agent reachable by two paths is restored once.
    agents: Dict[int, BaseAgent] = {}
    for child in children:
        for agent in _reachable_agents(child):
            agents[id(agent)] = agent
    return list(agents.values())


class ForEachNode:
    """
    Execute a node on each item in a collection.

    Items are independent: every item runs against the conversation history its
    agents had before the loop, so no item sees another item or its replies.

    Supports only sequential execution for now. (parallel execution would be supported in future)
    """

    def __init__(
        self,
        name: str,
        execute_node: 'AriumNodeType',
        input_filter: Optional[List[str]] = None,
        forward_all_results: bool = False,
    ):
        """
        Args:
            name: Node name
            execute_node: Node to execute on each item
            input_filter: Optional list of node names whose outputs this node
                iterates over (defaults to all items in memory)
            forward_all_results: When True, every per-item result is forwarded
                into workflow memory (each tagged with this node's name) so a
                downstream node can consume the whole collection via its own
                input_filter. When False (default), only the last item's result
                is forwarded, preserving the original behavior.
        """
        self.name = name
        self.execute_node = execute_node
        self.input_filter: Optional[List[str]] = input_filter
        self.forward_all_results: bool = forward_all_results

    async def _execute_item(
        self,
        item: Any,
        index: int,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute the node on a single item"""
        logger.info(f"ForEach '{self.name}': Processing item {index + 1}")

        # Create execution variables with item context
        item_variables = (variables or {}).copy()

        # Execute the node
        # Only ExecutableNode types have a run method
        if not isinstance(self.execute_node, ExecutableNode):
            raise TypeError(f'Node {self.execute_node.name} does not support execution')

        # Restored even on failure; shared agents make this sequential-only.
        histories = [
            (agent, list(agent.conversation_history))
            for agent in _reachable_agents(self.execute_node)
        ]
        try:
            result = await self.execute_node.run(
                inputs=[item],
                variables=item_variables,
            )
        finally:
            for agent, history in histories:
                agent.conversation_history = history
            # The item is done; its rendered pages would otherwise be held,
            # with every other item's, until the workflow returns.
            cache = getattr(getattr(item, 'content', None), '_formatted_cache', None)
            if isinstance(cache, dict):
                cache.clear()

        # Return last item if result is a list, otherwise return as-is
        if isinstance(result, list) and result:
            return result[-1]
        return result

    async def run(
        self, inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> List[Any]:
        """Execute the node on all items"""

        # Sequential execution
        results = []
        for i, item in enumerate(inputs):
            result = await self._execute_item(item, i, variables)
            results.append(result)

        logger.info(f"ForEach '{self.name}': Completed processing {len(results)} items")

        return results


class FunctionNode:
    """
    Lightweight function-as-node wrapper that conforms to ExecutableNode.

    Forwards inputs and variables to the provided function along with any kwargs.
    """

    def __init__(
        self,
        name: str,
        function: Callable[..., Any],
        description: Optional[str] = None,
        prefilled_params: Optional[Dict[str, Any]] = None,
        input_filter: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.description = description or f"Function node '{name}'"
        self.function = function
        self.prefilled_params = prefilled_params or {}
        self.input_filter: Optional[List[str]] = input_filter

    async def run(
        self,
        inputs: List[BaseMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        if asyncio.iscoroutinefunction(self.function):
            logger.info(f"Executing FunctionNode '{self.name}' as a coroutine function")
            result = await self.function(
                inputs=inputs, variables=variables, **self.prefilled_params, **kwargs
            )
            return UserMessage(content=result)

        logger.info(f"Executing FunctionNode '{self.name}' as a regular function")
        result = self.function(
            inputs=inputs, variables=variables, **self.prefilled_params, **kwargs
        )

        if asyncio.iscoroutine(result):
            logger.info(f"Executing FunctionNode '{self.name}' as a coroutine")
            content = await result
            return UserMessage(content=content)

        return UserMessage(content=result)
