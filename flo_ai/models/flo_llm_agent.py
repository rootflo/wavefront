from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from langchain.agents import create_tool_calling_agent
from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from flo_ai.helpers.utils import randomize_name
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.state.flo_session import FloSession
from typing import Union, Optional
from langchain_core.output_parsers import StrOutputParser

class FloLLMAgent(ExecutableFlo):

    def __init__(self, 
                 executor: Runnable, 
                 name: str) -> None:
        super().__init__(name, executor, "agent")
        self.executor: Runnable = executor

    class Builder:
        def __init__(self, 
                    session: FloSession,
                    name: str, 
                    prompt: Union[ChatPromptTemplate, str], 
                    role: Optional[str] = None,
                    llm: Union[BaseLanguageModel, None] =  None) -> None:
            self.name: str = randomize_name(name)
            self.llm = llm if llm is not None else session.llm
            # TODO improve to add more context of what other agents are available
            system_prompts = [("system", "You are a {}".format(role)), ("system", prompt)] if role is not None else [("system", prompt)]
            system_prompts.append(MessagesPlaceholder(variable_name="messages"))
            self.prompt: ChatPromptTemplate = ChatPromptTemplate.from_messages(
                system_prompts
            ) if isinstance(prompt, str) else prompt


        def build(self) -> Runnable:
            executor = self.prompt | self.llm | StrOutputParser()
            return FloLLMAgent(executor, self.name)
