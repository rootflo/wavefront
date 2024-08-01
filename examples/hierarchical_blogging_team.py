from flo_ai import Flo
from flo_ai.core import Flo
from langchain_openai import ChatOpenAI
from flo_ai import FloSession
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
load_dotenv()

yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: blogging-team
team:
    name: BloggingTeam
    supervisor:
        name: supervisor
    subteams:
        - name: BloggingTeam
          supervisor:
            name: supervisor
          agents:
            - name: Reasercher
              prompt: Do a research on the internet and find articles of relevent to the topic asked by the user, always try to find the latest information on the same
              tools:
              - name: TavilySearchResults
            - name: Blogger
              prompt: From the documents provider by the researcher write a blog of 300 words with can be readily published, make in engaging and add reference links to original blogs
              tools:
                - name: TavilySearchResults
        - name: Writing Team
          supervisor:
            name: supervisor
          agents: 
            - name: Figure
              prompt: Do somethinh
              tools:
                - name: TavilySearchResults
"""

input_prompt = """
Question: Write me an interesting blog about latest advancements in agentic AI
"""


llm = ChatOpenAI(temperature=0, model_name='gpt-4o')
session = FloSession(llm).register_tool(
    name="TavilySearchResults", tool=TavilySearchResults()
)
flo: Flo = Flo.build(session, llm, yaml=yaml_data)
