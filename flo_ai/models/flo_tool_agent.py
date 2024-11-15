from langchain_core.runnables import Runnable
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from flo_ai.yaml.config import AgentConfig
from flo_ai.models.flo_executable import ExecutableType


class FloToolAgent(ExecutableFlo):
    def __init__(
        self, executor: Runnable, config: AgentConfig, model_name: str
    ) -> None:
        super().__init__(config.name, executor, ExecutableType.tool)
        self.executor: Runnable = executor
        self.config: AgentConfig = config
        self.model_name: str = model_name

    class Builder:
        def __init__(
            self,
            session: FloSession,
            config: AgentConfig,
            tool_runnable: Runnable,
            model_name: str,
        ) -> None:
            self.name: str = config.name
            self.runnable = tool_runnable
            self.config = config
            self.model_name = model_name

        def build(self) -> Runnable:
            return FloToolAgent(self.runnable, self.configs, self, self.model_name)
