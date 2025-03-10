from flo_ai import FloSession, Flo
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv

load_dotenv()

yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: blogging-team
team:
    name: BloggingTeam
    router:
        name: BloggerTeamLead
        kind: supervisor
    agents:
      - name: Researcher
        role: Blog Researcher
        job: Generate a list of topics related to the user questions and accululate articles about them
        tools:
          - name: TavilySearchResults
      - name: Blogger
        role: Blog Writer
        job: From the documents provider by the researcher write a blog of 300 words with can be readily published, make in engaging and add reference links to original blogs
        tools:
          - name: TavilySearchResults
"""

input_prompt = """
Question: Write me an interesting blog about latest advancements in agentic AI by reasearching the internet
"""

llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
session = (
    FloSession(llm)
    .register_tool(name='TavilySearchResults', tool=TavilySearchResults())
    .register_tool(
        name='DummyTool',
        tool=TavilySearchResults(description='Tool is a dummy tool, dont use this'),
    )
)

Flo.set_log_level('INFO')
flo: Flo = Flo.build(session, yaml=yaml_data)
data = flo.invoke(input_prompt)
# print((data['messages'][-1]).content)
