from typing import Union, Optional
from langchain_core.runnables import Runnable
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_executable import ExecutableFlo
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableType
from langchain_core.output_parsers import StrOutputParser
from flo_ai.models.delegate import Delegate


class FloReflectionAgent(ExecutableFlo):
    def __init__(
        self, name: str, executor: Runnable, model_name: str, delegate: Delegate
    ) -> None:
        super().__init__(name, executor, ExecutableType.reflection)
        self.model_name = model_name
        self.delegate = delegate

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        job: str,
        to: Delegate,
        role: Optional[str] = None,
        llm: Optional[BaseLanguageModel] = None,
    ):
        model_name = 'default' if llm is None else llm.name
        return FloReflectionAgent.Builder(
            session=session,
            name=name,
            job=job,
            to=to,
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
            to: Delegate,
            role: Optional[str] = None,
            llm: Union[BaseLanguageModel, None] = None,
            model_name: str = None,
        ) -> None:
            prompt_message: Union[ChatPromptTemplate, str] = job
            self.name: str = name
            self.llm = llm if llm is not None else session.llm
            self.model_name = model_name
            self.delegate = to

            system_prompts = (
                [
                    ('system', 'You are a {}'.format(role)),
                    ('system', prompt_message),
                ]
                if role is not None
                else [('system', prompt_message)]
            )
            system_prompts.append(MessagesPlaceholder(variable_name='messages'))
            self.prompt: ChatPromptTemplate = (
                ChatPromptTemplate.from_messages(system_prompts)
                if isinstance(prompt_message, str)
                else prompt_message
            )

        def build(self):
            executor = self.prompt | self.llm | StrOutputParser()
            return FloReflectionAgent(
                self.name, executor, self.model_name, delegate=self.delegate
            )
