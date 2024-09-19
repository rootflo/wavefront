from flo_ai import Flo
from flo_ai.core import Flo
from langchain_openai import ChatOpenAI
from flo_ai import FloSession
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from dotenv import load_dotenv
load_dotenv()

from typing import Optional, Type
from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import BaseTool, StructuredTool, tool
from langchain.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
)

class FetchTrxInput(BaseModel):
    reference_number: str = Field(description="The transaction reference number")

class FetchTransactionTool(BaseTool):
    name = "fetch_transactions"
    description = "useful for when you want to fetch the transaction details given reference number"
    args_schema: Type[BaseModel] = FetchTrxInput

    def _run(
        self, reference_number: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        return "The transaction happened on 23/07/2024 IST and it failed because there was not enough balance in the account"

    async def _arun(
        self, reference_number: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        return "The transaction happened on 23/07/2024 IST and it failed because there was not enough balance in the account"

yaml_data = """
apiVersion: flo/alpha-v1
kind: FloRoutedTeam
name: data-processing
team:
    name: DataProcessing
    router:
        name: data-processing-pipline
        kind: linear
    agents:
          - name: Reasercher
            job: Do a research on the internet and find articles of relevent to the topic asked by the user, always try to find the latest information on the same
            tools:
                - name: TavilySearchResults
          - name: Blogger
            job: From the documents provider by the researcher write a blog of 300 words with can be readily published, make in engaging and add reference links to original blogs
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
flo: Flo = Flo.build(session, yaml=yaml_data)

for event in flo.stream(input_prompt):
    for k, v in event.items():
        if k != "__end__":
            print(v)
