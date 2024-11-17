from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from typing import Union, Optional
from langchain_core.output_parsers import StrOutputParser
from flo_ai.models.flo_executable import ExecutableType


class FloLLMAgent(ExecutableFlo):
    def __init__(self, name: str, executor: Runnable, model_name: str) -> None:
        super().__init__(name, executor, ExecutableType.llm)
        self.executor: Runnable = executor
        self.model_name: str = model_name

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        job: str,
        role: Optional[str] = None,
        llm: Union[BaseLanguageModel, None] = None,
    ):
        model_name = 'default' if llm is None else llm.name
        return FloLLMAgent.Builder(
            session=session,
            name=name,
            job=job,
            role=role,
            llm=llm,
            model_name=model_name,
        ).build()

    class Builder:
        def __init__(
            self,
            session: FloSession,
            name: str,
            job: str,
            role: Optional[str] = None,
            llm: Union[BaseLanguageModel, None] = None,
            model_name: str = None,
        ) -> None:
            self.model_name = model_name
            prompt: Union[ChatPromptTemplate, str] = job

            self.name: str = name
            self.llm = llm if llm is not None else session.llm
            # TODO improve to add more context of what other agents are available
            system_prompts = (
                [('system', 'You are a {}'.format(role)), ('system', prompt)]
                if role is not None
                else [('system', prompt)]
            )
            system_prompts.append(MessagesPlaceholder(variable_name='messages'))
            self.prompt: ChatPromptTemplate = (
                ChatPromptTemplate.from_messages(system_prompts)
                if isinstance(prompt, str)
                else prompt
            )

        def build(self) -> Runnable:
            executor = self.prompt | self.llm | StrOutputParser()
            return FloLLMAgent(self.name, executor, self.model_name)
