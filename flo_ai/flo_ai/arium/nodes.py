from flo_ai.arium.protocols import ExecutableNode
from typing import List, Any, Dict, Optional, TYPE_CHECKING
from flo_ai.utils.logger import logger

if TYPE_CHECKING:  # need to have an optional import else will get circular dependency error as arium also has AriumNode reference
    from flo_ai.arium.arium import Arium


class AriumNode:
    """
    Wrapper to use an Arium as a node in another Arium workflow.
    """

    def __init__(self, name: str, arium: 'Arium', inherit_variables: bool = True):
        """
        Args:
            name: Name for this node in the parent workflow
            arium: The Arium workflow to execute
            inherit_variables: Whether to pass parent variables to sub-workflow
        """
        self.name = name
        self.arium = arium
        self.inherit_variables = inherit_variables

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

    def __init__(self, name: str, execute_node: ExecutableNode):
        """
        Args:
            name: Node name
            execute_node: Node to execute on each item
        """
        self.name = name
        self.execute_node = execute_node

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
