from typing import Optional
from langchain_core.runnables import Runnable
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableType
from flo_ai.state.flo_output_collector import FloOutputCollector


class FloToolAgent(ExecutableFlo):
    def __init__(
        self,
        name: str,
        executor: Runnable,
        model_name: str,
        data_collector: Optional[FloOutputCollector] = None,
    ) -> None:
        super().__init__(name, executor, ExecutableType.tool)
        self.executor: Runnable = executor
        self.model_name: str = model_name
        self.data_collector = data_collector

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
            data_collector: Optional[FloOutputCollector] = None,
        ) -> None:
            self.name: str = name
            self.runnable = tool_runnable
            self.model_name = model_name
            self.data_collector = data_collector

        def build(self) -> Runnable:
            return FloToolAgent(
                self.name,
                self.runnable,
                self.model_name,
                data_collector=self.data_collector,
            )
