from flo_ai.core import Flo
from langchain_openai import ChatOpenAI
from xamples.enviroment import load_env

from flo_ai import FloSession
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
load_dotenv()

yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: blogging-team
team:
    planner:
        name: blog-planner
    name: BloggingTeam
    agents:
      - name: Reasercher
        prompt: Do a research on the internet and find articles of relevent to the topic asked by the user
        tools:
          - name: TavilySearchResults
      - name: BlogWriter
        prompt: Able to write a blog using information provided
        tools:
          - name: TavilySearchResults
"""

llm = ChatOpenAI(temperature=0, model_name='gpt-4o')
session = FloSession(llm).register_tool(
    name="TavilySearchResults", 
    tool=TavilySearchResults()
)
flo: Flo = Flo.build(llm, yaml=yaml_data)
image_data = flo.draw_to_file("examples/images/agent-planned-graph.png")

config = {"recursion_limit": 50}
inputs = "Write a interesting blog about Sachin Tendulkar vs Brian Lara?"
for event in flo.stream(inputs, config=config):
    for k, v in event.items():
        if k != "__end__":
            print(v)