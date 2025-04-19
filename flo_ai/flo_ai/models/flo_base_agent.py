from typing import Optional
from langchain_core.runnables import Runnable
from flo_ai.models.flo_executable import ExecutableFlo, ExecutableType
from flo_ai.state.flo_output_collector import FloOutputCollector


class FloBaseAgent(ExecutableFlo):
    """Base class for all Flo agents containing common properties and initialization."""

    def __init__(
        self,
        name: str,
        executor: Runnable,
        executable_type: ExecutableType,
        model_name: str,
        data_collector: Optional[FloOutputCollector] = None,
    ) -> None:
        """Initialize the base agent with common properties.

        Args:
            name: Name of the agent
            executor: The runnable executor for the agent
            executable_type: Type of the executable
            model_name: Name of the model being used
            data_collector: Optional collector for output data
        """
        super().__init__(name, executor, executable_type)
        self.executor: Runnable = executor
        self.model_name: str = model_name
        self.members = []
        self.data_collector: Optional[FloOutputCollector] = data_collector
