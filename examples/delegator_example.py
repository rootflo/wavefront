from flo_ai.core import Flo
from flo_ai import FloSession
from langchain_openai import ChatOpenAI
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
load_dotenv()

yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: adding-team
team:
    name: EssayTeam
    agents:
      - name: EssayWriter
        kind: llm
        job: >
          You are an essay assistant tasked with writing excellent 300 words essay. Generate the best essay possible for the user's request. 
          If the you are provided critique view, respond with a revised version of your previous attempts. A maximum of total 100 words
      - name: DelegatorAgent
        kind: delegator
        retry: 1
        to: 
          - name: EssayWriter
        job: >
          You are a teacher grading an essay submission. Score the essay between 1 to 10, with 10 being perfect
          If the score is greater than 7 sent it to FinalEssayProducer
          else if its less than or equal to 7 sent it to EssayWriter with suggestions to change
      - name: FinalEssayProducer
        kind: llm
        job: >
          Generate the final assay to be returned to the user
    router:
      name: router
      kind: linear
"""

input_prompt = """
Question: Write me an interesting blog about latest advancements in agentic AI by reasearching the internet
"""

llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')
session = FloSession(llm).register_tool(
    name="TavilySearchResults", 
    tool=TavilySearchResults()
)

flo: Flo = Flo.build(session, yaml=yaml_data)
flo.draw_to_file("delegate.png", xray=True)
# data = flo.invoke(input_prompt)
# print((data['messages'][-1]).content)