import asyncio
from langchain.tools import tool
from functools import wraps
from typing import Optional
from flo_ai.constants.common_constants import DOCUMENTATION_AGENT_TOOLS
from flo_ai.error.flo_exception import FloException

def flotool(
        name: str, 
        description: Optional[str] = None,
        argument_contract: Optional[type] = None, 
        unsafe: bool = False):
    
    def decorator(func):
        func.__doc__ = func.__doc__ or description
        
        @tool(name, args_schema=argument_contract)
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if unsafe:
                    raise e
                return f"An error occurred while executing the tool: {str(e)}, please retry with the corresponding fix"
        
    
        @tool(name, args_schema=argument_contract)
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if unsafe:
                    raise e
                return f"An error occurred while executing the tool: {str(e)}, please retry with the corresponding fix"
            
        return async_wrapper if asyncio.iscoroutinefunction(func) else wrapper
    
    return decorator
