from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor
from langchain.agents import create_tool_calling_agent
from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from typing import Union, Optional, Callable
from flo_ai.models.flo_executable import ExecutableType


class FloAgent(ExecutableFlo):
    def __init__(
        self,
        name: str,
        agent: Runnable,
        executor: AgentExecutor,
        model_name: str,
    ) -> None:
        super().__init__(name, executor, ExecutableType.agentic)
        self.model_name = model_name
        self.agent: Runnable = (agent,)
        self.executor: AgentExecutor = executor

    @staticmethod
    def create(
        session: FloSession,
        name: str,
        job: str,
        tools: list[BaseTool],
        role: Optional[str] = None,
        on_error: Union[str, Callable] = True,
        llm: Union[BaseLanguageModel, None] = None,
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
        ) -> None:
            prompt: Union[ChatPromptTemplate, str] = job
            self.name: str = name
            self.model_name = model_name
            self.llm = llm if llm is not None else session.llm
            system_prompts = (
                [('system', 'You are a {}'.format(role)), ('system', prompt)]
                if role is not None
                else [('system', prompt)]
            )
            system_prompts.append(MessagesPlaceholder(variable_name='messages'))
            system_prompts.append(MessagesPlaceholder(variable_name='agent_scratchpad'))
            self.prompt: ChatPromptTemplate = (
                ChatPromptTemplate.from_messages(system_prompts)
                if isinstance(prompt, str)
                else prompt
            )
            self.tools: list[BaseTool] = tools
            self.verbose = verbose
            self.on_error = on_error

        def build(self) -> AgentExecutor:
            agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
            executor = AgentExecutor(
                agent=agent,
                tools=self.tools,
                verbose=self.verbose,
                return_intermediate_steps=True,
                handle_parsing_errors=self.on_error,
            )
            return FloAgent(self.name, agent, executor, model_name=self.model_name)
