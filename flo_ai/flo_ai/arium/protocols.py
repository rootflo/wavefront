from typing import Protocol, runtime_checkable, List, Any, Dict, Optional


@runtime_checkable
class ExecutableNode(Protocol):
    """
    Protocol defining the interface for any node that can be executed
    within an Arium workflow.

    Any class implementing this protocol can be used as a node:
    - Agent (already implements)
    - Tool (already implements)
    - Arium (already implements!)
    - Custom node types
    """

    name: str
    """Unique identifier for the node"""
    input_filter: Optional[List[str]] = None
    """List of input keys to include in the node's execution"""

    async def run(
        self,
        inputs: List[str | Any],
        variables: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Any:
        """
        Execute the node and return results.

        Args:
            inputs: Input data for execution
            variables: Optional variable substitutions
            **kwargs: Additional execution parameters

        Returns:
            Execution result (type depends on node implementation)
        """
        ...
