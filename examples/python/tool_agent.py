from flo_ai import Flo
from flo_ai import FloSession
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv
from langchain.tools import BaseTool

load_dotenv()


llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')

session = FloSession(llm, log_level='ERROR')


class PrintStateTool(BaseTool):
    name: str = 'printStateTool'
    description: str = 'Just print the state'

    def _run(self, **kwargs) -> str:
        return 'Print tool call success'


session.register_tool(name='printStateTool', tool=PrintStateTool())

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

flo = Flo.build(session, simple_tool_agent, log_level='ERROR')

print(flo.invoke('Testing ....'))
