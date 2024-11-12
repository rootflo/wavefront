from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from typing import Union
from langchain_core.output_parsers import StrOutputParser
from flo_ai.yaml.config import AgentConfig
from flo_ai.models.flo_executable import ExecutableType


class FloLLMAgent(ExecutableFlo):
    def __init__(self, executor: Runnable, config: AgentConfig) -> None:
        super().__init__(config.name, executor, ExecutableType.llm)
        self.executor: Runnable = executor
        self.config: AgentConfig = config

    class Builder:
        def __init__(
            self,
            session: FloSession,
            config: AgentConfig,
            llm: Union[BaseLanguageModel, None] = None,
        ) -> None:
            prompt: Union[ChatPromptTemplate, str] = config.job

            self.name: str = config.name
            self.llm = llm if llm is not None else session.llm
            # TODO improve to add more context of what other agents are available
            system_prompts = (
                [('system', 'You are a {}'.format(config.role)), ('system', prompt)]
                if config.role is not None
                else [('system', prompt)]
            )
            system_prompts.append(MessagesPlaceholder(variable_name='messages'))
            self.prompt: ChatPromptTemplate = (
                ChatPromptTemplate.from_messages(system_prompts)
                if isinstance(prompt, str)
                else prompt
            )
            self.config = config

        def build(self) -> Runnable:
            executor = self.prompt | self.llm | StrOutputParser()
            return FloLLMAgent(executor, self.config)
