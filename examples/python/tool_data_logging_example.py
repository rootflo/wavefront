from flo_ai.callbacks import FloExecutionLogger
from flo_ai.storage.data_collector import JSONLFileCollector
from langchain_openai import AzureChatOpenAI
import os
from dotenv import load_dotenv
from flo_ai import Flo
from flo_ai import FloSession
from typing import List
from flo_ai.tools import flotool

load_dotenv()

llm = AzureChatOpenAI(
    temperature=0,
    deployment_name='gpt-4',
    model_name='gpt-4',
    azure_endpoint=os.getenv('AZURE_OPENAI_ENDPOINT'),
    api_key=os.getenv('AZURE_OPENAI_API_KEY'),
    api_version='2024-08-01-preview',
)

session = FloSession(
    llm,
    log_level='ERROR',
)


@flotool(name='AdditionTool', description='Tool to add numbers')
def addition_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    return f'The sum is {result}'


@flotool(
    name='MultiplicationTool',
    description='Tool to multiply numbers to get product of numbers',
)
def mul_tool(numbers: List[int]) -> str:
    result = 1
    for num in numbers:
        result *= num
    return f'The product is {result}'


session.register_tool(name='Adder', tool=addition_tool).register_tool(
    name='Multiplier', tool=mul_tool
)

simple_calculator_agent = """
apiVersion: flo/alpha-v1
kind: FloAgent
name: calculating-assistant
agent:
    name: SummationHelper
    kind: agentic
    job: >
      You are a calculation assistant that MUST ONLY use the provided tools for calculations.
      You MUST ONLY return the exact outputs from the tools without modification.
      You MUST NOT perform any calculations yourself.
      If you need both sum and product, you MUST use both tools and combine their exact outputs.
    tools:
      - name: Adder
      - name: Multiplier
"""


current_dir = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(current_dir, 'my_llm_logs.jsonl')

file_collector = JSONLFileCollector(log_file_path)
local_tracker = FloExecutionLogger(file_collector)

session.register_callback(local_tracker)

flo = Flo.build(session, simple_calculator_agent, log_level='ERROR')

result = flo.invoke(
    'find the sum of first three numbers and last three numbers and multilply the result. Numbers are 1, 3, 4, 2, 0, 1',
)
