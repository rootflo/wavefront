from langchain.pydantic_v1 import BaseModel, Field
from langchain.tools import Tool
from langchain_core.runnables import Runnable
from functools import partial

class FloRagToolInput(BaseModel):
    query: str = Field(description="query to look up in retriever")
    
def __get_rag_answer(query: str, runnable: Runnable):
    result = runnable.invoke({ "question": query })
    return result["answer"].content

async def __aget_rag_answer(query: str, runnable: Runnable):
    result = await runnable.ainvoke({ "question": query })
    return result["answer"].content

def create_flo_rag_tool(
    runnable_rag: Runnable,
    name: str,
    description: str
) -> Tool:
    func = partial(
        __get_rag_answer,
        runnable=runnable_rag
    )

    afunc = partial(
        __aget_rag_answer,
        runnable=runnable_rag
    )
    
    return Tool(
        name=name,
        description=description,
        func=func,
        coroutine=afunc,
        args_schema=FloRagToolInput,
    )

