import pytest
import asyncio
from typing import List
from flo_ai.tools.flo_tool import flotool

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