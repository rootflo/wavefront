from flo_ai.arium.protocols import ExecutableNode
from typing import List, Any, Dict, Optional, TYPE_CHECKING, Callable
from flo_ai.utils.logger import logger
from flo_ai.arium.memory import MessageMemory
from flo_ai.models import BaseMessage, UserMessage
import asyncio

if TYPE_CHECKING:  # need to have an optional import else will get circular dependency error as arium also has AriumNode reference
    from flo_ai.arium.arium import Arium


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
            variables.copy() if (self.inherit_variables and variables) else None
        )

        # Execute the nested Arium with isolated memory
        result = await self.arium.run(
            inputs=inputs,
            variables=execution_variables,
        )
        return result


class ForEachNode:
    """
    Execute a node on each item in a collection.

    Supports only sequential execution for now. (parallel execution would be supported in future)
    """

    def __init__(
        self,
        name: str,
        execute_node: ExecutableNode,
        input_filter: Optional[List[str]] = None,
    ):
        """
        Args:
            name: Node name
            execute_node: Node to execute on each item
        """
        self.name = name
        self.execute_node = execute_node
        self.input_filter: Optional[List[str]] = input_filter

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
        result = await self.execute_node.run(
            inputs=[item],
            variables=item_variables,
        )

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

    async def _execute_item_with_isolated_memory(
        self,
        item: Any,
        index: int,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Execute the node on a single item with isolated memory.
        This prevents memory accumulation across iterations.
        """
        logger.info(
            f"ForEach '{self.name}': Processing item {index + 1} with isolated memory"
        )

        # Create execution variables with item context
        item_variables = (variables or {}).copy()

        # If the execute_node is an AriumNode, we can create a new memory instance
        if hasattr(self.execute_node, 'arium') and hasattr(
            self.execute_node.arium, 'memory'
        ):
            # Create a new memory instance for this iteration
            original_memory = self.execute_node.arium.memory
            self.execute_node.arium.memory = MessageMemory()

            try:
                # Execute the node with isolated memory
                result = await self.execute_node.run(
                    inputs=[item],
                    variables=item_variables,
                )
            finally:
                # Restore original memory
                self.execute_node.arium.memory = original_memory
        else:
            # For non-Arium nodes, execute normally
            result = await self.execute_node.run(
                inputs=[item],
                variables=item_variables,
            )

        # Return last item if result is a list, otherwise return as-is
        if isinstance(result, list) and result:
            return result[-1]
        return result


class FunctionNode:
    """
    Lightweight function-as-node wrapper that conforms to ExecutableNode.

    Forwards inputs and variables to the provided function along with any kwargs.
    """

    def __init__(
        self,
        name: str,
        description: str,
        function: Callable[..., Any],
        input_filter: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.function = function
        self.input_filter: Optional[List[str]] = input_filter

    async def run(
        self,
        inputs: List[BaseMessage] | str,
        variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        logger.info(
            f"Executing FunctionNode '{self.name}' with inputs: {inputs} variables: {variables} kwargs: {kwargs}"
        )

        if asyncio.iscoroutinefunction(self.function):
            logger.info(f"Executing FunctionNode '{self.name}' as a coroutine function")
            result = await self.function(inputs=inputs, variables=variables, **kwargs)
            return UserMessage(content=result)

        if asyncio.iscoroutine(result):
            logger.info(f"Executing FunctionNode '{self.name}' as a coroutine")
            content = await result
            return UserMessage(content=content)

        logger.info(f"Executing FunctionNode '{self.name}' as a regular function")
        result = self.function(inputs=inputs, variables=variables, **kwargs)
        return UserMessage(content=result)
