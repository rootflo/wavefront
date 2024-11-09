from flo_ai import Flo
from flo_ai import FloSession
from langchain_openai import ChatOpenAI
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from typing import List
from dotenv import load_dotenv
from flo_ai.tools.flo_tool import flotool

load_dotenv()

llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini')

session = FloSession(
    llm, 
    log_level="ERROR"
)

class AdditionToolInput(BaseModel):
    numbers: List[int] = Field(..., description="List of numbers to add")

import asyncio
# Use flotool to define the tool function
@flotool(name="AdditionTool", description="Tool to add numbers")
async def addition_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    await asyncio.sleep(1) 
    return f"The sum is {result}"

@flotool(name="MultiplicationTool", description="Tool to multiply numbers to get product of numbers")
def mul_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    # await asyncio.sleep(1) 
    return f"The product is {result}"

session.register_tool(
    name="Adder", 
    tool=addition_tool
).register_tool(
    name="Multiplier", 
    tool=mul_tool
)

simple_weather_checking_agent = """
apiVersion: flo/alpha-v1
kind: FloAgent
name: weather-assistant
agent:
    name: SummationHelper
    kind: agentic
    job: >
      Add or multiply numbers. Always answer based on what the tool says
    tools:
      - name: Adder
      - name: Multiplier
"""

from IPython.display import Image, display
flo = Flo.build(session, simple_weather_checking_agent, log_level="ERROR")

import asyncio

# Assuming flo.ainvoke is your async method for invoking the tool or chain
async def invoke_main():
    result = await flo.async_invoke("Whats the sum of 1, 3, 4, 5 and 6, and their product")
    print(result)

asyncio.run(invoke_main())

# import asyncio

# async def stream_main():
#     # Use 'async for' to iterate over the asynchronous generator
#     async for s in flo.async_stream("Whats the sum of 1, 3, 4, 5 and 6, and their product"):
#         if "__end__" not in s:
#             print(s)
#             print("----")

# asyncio.run(stream_main())



