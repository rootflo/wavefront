from langchain_core.runnables import Runnable
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from flo_ai.yaml.config import AgentConfig
from flo_ai.models.flo_executable import ExecutableType


class FloToolAgent(ExecutableFlo):
    def __init__(self, executor: Runnable, config: AgentConfig) -> None:
        super().__init__(config.name, executor, ExecutableType.tool)
        self.executor: Runnable = executor
        self.config: AgentConfig = config

    class Builder:
        def __init__(
            self, session: FloSession, config: AgentConfig, tool_runnable: Runnable
        ) -> None:
            self.name: str = config.name
            self.runnable = tool_runnable
            self.config = config

        def build(self) -> Runnable:
            return FloToolAgent(self.runnable, self.config)
