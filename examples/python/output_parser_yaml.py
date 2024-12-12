import os
from flo_ai import FloSession, Flo
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from flo_ai.state.flo_kv_collector import FloKVCollector

load_dotenv()
llm = AzureChatOpenAI(
    azure_endpoint=os.getenv('AZURE_GPT4_ENDPOINT'),
    model_name='gpt-4o',
    temperature=0.2,
    max_tokens=4096,
    api_version='2024-08-01-preview',
    api_key=os.getenv('AZURE_OPEN_AI_API_KEY'),
)

session = FloSession(llm).register_tool(
    name='InternetSearchTool', tool=TavilySearchResults()
)

dc = FloKVCollector()

session.register_data_collector('kv', dc)

simple_reseacher = """
apiVersion: flo/alpha-v1
kind: FloAgent
name: weather-assistant
agent:
    name: WeatherAssistant
    kind: agentic
    job: >
      Given the person name, guess the first and last name
    tools:
      - name: InternetSearchTool
    parser:
        name: NameFormatter
        fields:
            - type: str
              description: The first name of the person
              name: first_name
            - type: str
              description: The first name of the person
              name: last_name
    data_collector: kv
"""

flo: Flo = Flo.build(session, simple_reseacher)
result = flo.invoke('Gandhi')

print(dc.fetch())
