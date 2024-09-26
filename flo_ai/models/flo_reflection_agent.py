from typing import Union
from langchain_core.runnables import Runnable
from flo_ai.yaml.config import AgentConfig
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableFlo
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableType
from langchain_core.output_parsers import StrOutputParser


class FloReflectionAgent(ExecutableFlo):

    def __init__(self, executor: Runnable, config: AgentConfig) -> None:
        super().__init__(config.name, executor, ExecutableType.reflection)
        self.config = config

    class Builder():
        def __init__(self, 
                    session: FloSession,
                    config: AgentConfig,
                    llm: Union[BaseLanguageModel, None] =  None) -> None:
            
            prompt_message: Union[ChatPromptTemplate, str] = config.job
            self.name: str = config.name
            self.llm = llm if llm is not None else session.llm
            self.config = config

            system_prompts = [("system", "You are a {}".format(config.role)), ("system", prompt_message)] if config.role is not None else [("system", prompt_message)]
            system_prompts.append(MessagesPlaceholder(variable_name="messages"))
            self.prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
                system_prompts
            ) if isinstance(prompt_message, str) else prompt_message

        def build(self):
            executor = self.prompt | self.llm | StrOutputParser()
            return FloReflectionAgent(executor, self.config)