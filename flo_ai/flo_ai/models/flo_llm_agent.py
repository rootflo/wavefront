from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from typing import Union, Optional
from langchain_core.output_parsers import StrOutputParser
from flo_ai.models.flo_executable import ExecutableType
from flo_ai.parsers.flo_parser import FloParser
from flo_ai.state.flo_output_collector import FloOutputCollector


class FloLLMAgent(ExecutableFlo):
    def __init__(
        self,
        name: str,
        executor: Runnable,
        model_name: str,
        data_collector: Optional[FloOutputCollector] = None,
    ) -> None:
        super().__init__(name, executor, ExecutableType.llm)
        self.executor: Runnable = executor
        self.model_name: str = model_name
        self.data_collector = data_collector

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        job: str,
        role: Optional[str] = None,
        llm: Union[BaseLanguageModel, None] = None,
        parser: Optional[FloParser] = None,
        data_collector: Optional[FloOutputCollector] = None,
    ):
        model_name = 'default' if llm is None else llm.name
        return FloLLMAgent.Builder(
            session=session,
            name=name,
            job=job,
            role=role,
            llm=llm,
            model_name=model_name,
            parser=parser,
            data_collector=data_collector,
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
            parser: Optional[FloParser] = None,
            data_collector: Optional[FloOutputCollector] = None,
        ) -> None:
            self.model_name = model_name
            prompt: Union[ChatPromptTemplate, str] = job

            self.name: str = name
            self.llm = llm if llm is not None else session.llm
            system_prompts = (
                [('system', 'You are a {}, {}'.format(role, prompt))]
                if role is not None
                else [('system', prompt)]
            )
            if parser is not None:
                system_prompts.append('\n{format_instructions}')
            system_prompts.append(MessagesPlaceholder(variable_name='messages'))
            self.prompt: ChatPromptTemplate = (
                ChatPromptTemplate.from_messages(system_prompts)
                if isinstance(prompt, str)
                else prompt
            )
            if parser is not None:
                self.prompt = self.prompt.partial(
                    format_instructions=parser.get_format_instructions()
                )
            self.data_collector = data_collector

        def build(self) -> Runnable:
            executor = self.prompt | self.llm | StrOutputParser()
            return FloLLMAgent(
                self.name, executor, self.model_name, data_collector=self.data_collector
            )
