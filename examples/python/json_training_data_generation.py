import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from flo_ai.callbacks import FloExecutionLogger
from flo_ai.storage.data_collector import JSONLFileCollector
from flo_ai import Flo, FloSession
from flo_ai.models.flo_agent import FloAgent
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv


load_dotenv()

file_collector = JSONLFileCollector('.logs')

# Create a tool logger with the collector
local_tracker = FloExecutionLogger(file_collector)
# Create the LLM object
llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')


prompt = PromptTemplate.from_template('1 + {number} = ')

chain = prompt | llm
print(chain.invoke({'number': 2}))


session = FloSession(llm)
session.register_callback(local_tracker)

os.environ['TAVILY_API_KEY'] = os.getenv('TAVILY_API_KEY')
tavily_tool = TavilySearchResults()

session.register_tool('thappal', tavily_tool)

weather_agent = FloAgent.create(
    session=session,
    name='Blogger',
    job='You can research the internet and create a blog about the topic given by the user',
    tools=[tavily_tool],
)


agent_flo: Flo = Flo.create(session, weather_agent)

print(agent_flo.invoke('Whats the whether in New Delhi, India ?'))
