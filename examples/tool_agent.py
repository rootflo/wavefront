from flo_ai import Flo
from flo_ai import FloSession
from flo_ai.common.flo_logger import get_logger
from flo_ai.common.flo_langchain_logger import FloLangchainLogger
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from dotenv import load_dotenv
load_dotenv()

from langchain_community.tools.tavily_search.tool import TavilySearchResults
from flo_ai.common.flo_langchain_logger import FloLangchainLogger

llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')

session = FloSession(
    llm, 
    log_level="ERROR"
)

from langchain.tools import BaseTool

class PrintStateTool(BaseTool):
    name = "printStateTool"
    description = "Just print the state"

    def _run(
        self, **kwargs
    ) -> str:
        return "Print tool call success"
    
session.register_tool(
    name="printStateTool", 
    tool=PrintStateTool()
)
    
simple_tool_agent = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: llm-assistant
team:
    name: tool-to-print-state
    router:
        name: LinearRouter
        kind: linear
    agents:
      - name: tool-to-print
        kind: tool
        tools:
          - name: printStateTool
"""

flo = Flo.build(session, simple_tool_agent, log_level="ERROR")

print(flo.invoke("Testing ...."))