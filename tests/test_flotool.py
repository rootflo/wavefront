import pytest
import asyncio
from typing import List
from flo_ai import Flo
from flo_ai.error.flo_exception import FloException
from langchain_openai import ChatOpenAI
from flo_ai.tools.flo_tool import flotool
from flo_ai.state.flo_session import FloSession
from flo_ai.constants.common_constants import DOCUMENTATION_WEBSITE

@flotool(name="AdditionTool", description="Tool to add numbers")
async def addition_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    await asyncio.sleep(1) 
    return f"The sum is {result}"

@flotool(name="MultiplicationTool", description="Tool to multiply numbers to get product of numbers")
def mul_tool(numbers: List[int]) -> str:
    result = sum(numbers)
    return f"The product is {result}"

def test_flotool_async():
    built_tool = asyncio.iscoroutinefunction(addition_tool.coroutine)
    assert built_tool

def test_flotool_sync():
    built_tool = asyncio.iscoroutinefunction(mul_tool.coroutine)
    assert not built_tool

@pytest.mark.asyncio
async def test_flotool_invoke_with_async_tool():
    result = await addition_tool.ainvoke({"numbers": [1, 32, 2]})
    assert f"The sum is 35" == result

def test_flotool_invoke_with_sync_tool():
    result = mul_tool.invoke({"numbers": [1, 32, 2]})
    assert f"The product is 35" == result

def test_session_registration_and_invoke():
    llm = ChatOpenAI(temperature=0, model_name='gpt-4o-mini', api_key="TEST_KEY")
    session = FloSession(llm)
    session.register_tool("adder", addition_tool)
    session.register_tool("muller", mul_tool)

    mock_agent_yaml = mock_agent_yaml = """
        apiVersion: flo/alpha-v1
        kind: FloAgent
        name: weather-assistant
        agent:
            name: WeatherAssistant
            kind: agentic
            job: >
                Given the city name you are capable of answering the latest whether this time of the year by searching the internet
            tools:
            - name: adder
    """

    flo = Flo.build(session, mock_agent_yaml)
    try:
        flo.invoke("What the whether in berlin")
    except FloException as e:
        assert str(e) == f"[Error -1] You seem to have atleast one async tool registered in this session. Please use flo.async_invoke or flo.async_stream. Checkout {DOCUMENTATION_WEBSITE}"