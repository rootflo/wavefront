from langchain_core.tools import BaseTool
from langchain.agents import AgentExecutor
from langchain.agents import create_tool_calling_agent
from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.helpers.utils import randomize_name
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from typing import Union, Optional

class FloAgent(ExecutableFlo):
    def __init__(self,
                 agent: Runnable, 
                 executor: AgentExecutor, 
                 name: str) -> None:
        super().__init__(name, executor, "agent")
        self.agent: Runnable =  agent,
        self.executor: AgentExecutor = executor

    class Builder:
        def __init__(self, 
                    session: FloSession,
                    name: str, 
                    prompt: Union[ChatPromptTemplate, str], 
                    tools: list[BaseTool],
                    verbose: bool = True,
                    role: Optional[str] = None,
                    llm: Union[BaseLanguageModel, None] =  None,
                    return_intermediate_steps: bool = False,
                    handle_parsing_errors: bool = True) -> None:
            self.name: str = randomize_name(name)
            self.llm = llm if llm is not None else session.llm
            # TODO improve to add more context of what other agents are available
            system_prompts = [("system", "You are a {}".format(role)), ("system", prompt)] if role is not None else [("system", prompt)]
            system_prompts.append(MessagesPlaceholder(variable_name="messages"))
            system_prompts.append(MessagesPlaceholder(variable_name="agent_scratchpad"))
            self.prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
                system_prompts
            ) if isinstance(prompt, str) else prompt
            self.tools: list[BaseTool] = tools
            self.verbose = verbose
            self.return_intermediate_steps = return_intermediate_steps
            self.handle_parsing_errors = handle_parsing_errors


        def build(self) -> AgentExecutor:
            agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
            executor = AgentExecutor(agent=agent, 
                                tools=self.tools, 
                                verbose=self.verbose, 
                                return_intermediate_steps=self.return_intermediate_steps, 
                                handle_parsing_errors=self.handle_parsing_errors)
            return FloAgent(agent, executor, self.name)
