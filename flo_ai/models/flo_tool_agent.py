from langchain_core.runnables import Runnable
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableType


class FloToolAgent(ExecutableFlo):
    def __init__(self, name: str, executor: Runnable, model_name: str) -> None:
        super().__init__(name, executor, ExecutableType.tool)
        self.executor: Runnable = executor
        self.model_name: str = model_name

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        tool: Runnable,
    ):
        model_name = 'default'
        return FloToolAgent.Builder(
            session=session,
            name=name,
            tool_runnable=tool,
            model_name=model_name,
        ).build()

    class Builder:
        def __init__(
            self,
            session: FloSession,
            name: str,
            tool_runnable: Runnable,
            model_name: str,
        ) -> None:
            self.name: str = name
            self.runnable = tool_runnable
            self.model_name = model_name

        def build(self) -> Runnable:
            return FloToolAgent(self.name, self.runnable, self.model_name)
