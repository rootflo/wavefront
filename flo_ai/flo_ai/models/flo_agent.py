from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor
from langchain.agents import create_tool_calling_agent
from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableFlo, ExecutableType
from flo_ai.state.flo_session import FloSession
from typing import Union, Optional, Callable
from flo_ai.state.flo_output_collector import FloOutputCollector
from flo_ai.parsers.flo_parser import FloParser


class FloAgent(ExecutableFlo):
    def __init__(
        self,
        name: str,
        agent: Runnable,
        executor: AgentExecutor,
        model_name: str,
        data_collector: Optional[FloOutputCollector] = None,
    ) -> None:
        super().__init__(name, executor, ExecutableType.agentic)
        self.model_name = model_name
        self.agent: Runnable = (agent,)
        self.executor: AgentExecutor = executor
        self.data_collector = data_collector

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        job: str,
        tools: list[BaseTool],
        role: Optional[str] = None,
        on_error: Union[str, Callable] = True,
        llm: Union[BaseLanguageModel, None] = None,
        parser: Optional[FloParser] = None,
        data_collector: Optional[FloOutputCollector] = None,
    ):
        model_name = 'default' if llm is None else llm.name
        return FloAgent.Builder(
            session=session,
            name=name,
            job=job,
            tools=tools,
            role=role,
            on_error=on_error,
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
            tools: list[BaseTool],
            role: Optional[str] = None,
            verbose: bool = False,
            llm: Union[BaseLanguageModel, None] = None,
            on_error: Union[str, Callable] = True,
            model_name: Union[str, None] = 'default',
            parser: Optional[FloParser] = None,
            data_collector: Optional[FloOutputCollector] = None,
        ) -> None:
            prompt: Union[ChatPromptTemplate, str] = job
            self.name: str = name
            self.model_name = model_name
            self.llm = llm if llm is not None else session.llm
            system_prompts = (
                [('system', 'You are a {}, {}'.format(role, prompt))]
                if role is not None
                else [('system', prompt)]
            )
            if parser is not None:
                system_prompts.append('\n{format_instructions}')
            system_prompts.append(MessagesPlaceholder(variable_name='messages'))
            system_prompts.append(MessagesPlaceholder(variable_name='agent_scratchpad'))
            self.prompt: ChatPromptTemplate = (
                ChatPromptTemplate.from_messages(system_prompts)
                if isinstance(prompt, str)
                else prompt
            )
            if parser is not None:
                self.prompt = self.prompt.partial(
                    format_instructions=parser.get_format_instructions()
                )
            self.tools: list[BaseTool] = tools
            self.verbose = verbose
            self.on_error = on_error
            self.data_collector = data_collector

        def build(self) -> AgentExecutor:
            agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
            executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=self.verbose,
                return_intermediate_steps=True,
                handle_parsing_errors=self.on_error,
            )
            return FloAgent(
                self.name,
                agent,
                executor,
                model_name=self.model_name,
                data_collector=self.data_collector,
            )
