import os
from flo_ai import FloAgent, FloSession, Flo
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from flo_ai.parsers.flo_json_parser import FloJsonParser
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
    name='TavilySearchResults', tool=TavilySearchResults()
)

format = {
    'name': 'NameFormat',
    'fields': [
        {
            'type': 'str',
            'description': 'The first name of the person',
            'name': 'first_name',
        },
        {
            'type': 'str',
            'description': 'The middle name of the person',
            'name': 'middle_name',
        },
        {
            'type': 'literal',
            'description': 'The last name of the person, the value can be either of Vishnu or Satis',
            'name': 'last_name',
            'values': [
                {'value': 'Vishnu', 'description': 'If the first_name starts with K'},
                {'value': 'Satis', 'description': 'If the first_name starts with M'},
            ],
            'default_value_prompt': 'If none of the above value is suited, please use value other than the above in snake-case',
        },
    ],
}

dc = FloKVCollector()

researcher = FloAgent.create(
    session,
    name='Researcher',
    role='Internet Researcher',
    job='What is the first name, last name  and middle name of the the person user asks about',
    tools=[TavilySearchResults()],
    parser=FloJsonParser.create(json_dict=format),
    data_collector=dc,
)


Flo.set_log_level('DEBUG')
flo: Flo = Flo.create(session, researcher)
result = flo.invoke('Mahatma Gandhi')

print(result)
print(dc.fetch())
