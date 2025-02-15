from flo_ai import FloLLMAgent, FloSession, Flo
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from flo_ai.parsers import FloJsonParser
from flo_ai.state import FloJsonOutputCollector
from flo_ai.callbacks import FloExecutionLogger
from flo_ai.storage.data_collector import JSONLFileCollector

load_dotenv()
llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')

session = FloSession(llm).register_tool(
    name='TavilySearchResults', tool=TavilySearchResults()
)


file_collector = JSONLFileCollector('.logs')

local_tracker = FloExecutionLogger(file_collector)

session.register_callback(local_tracker)

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

dc = FloJsonOutputCollector()

researcher = FloLLMAgent.create(
    session,
    name='Formatter',
    role='Output formatter',
    job='What is the first name, last name  and middle name of the the person user asks about',
    parser=FloJsonParser.create(json_dict=format),
    data_collector=dc,
)


Flo.set_log_level('DEBUG')
flo: Flo = Flo.create(session, researcher)
result = flo.invoke('Mahatma Gandhi')

print(result)
print(dc.fetch())
