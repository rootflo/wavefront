import logging
from typing import Dict, Any, Callable, List, Optional
from flo_ai.models.agent_error import AgentError
from flo_ai.utils.logger import logger

# Characters of a tool result shown in its log line.
TOOL_RESULT_PREVIEW_CHARS = 200


def describe_tool_result(result: Any) -> str:
    """A tool result's type and size, never its content."""
    if isinstance(result, str):
        return f'str[{len(result)} chars]'
    if isinstance(result, (list, tuple, dict, set)):
        return f'{type(result).__name__}[{len(result)} items]'
    mime_type = getattr(result, 'mime_type', None)
    name = type(result).__name__
    return f'{name}({mime_type})' if mime_type else name


def log_tool_result(label: str, result: Any) -> None:
    """Results can be whole query results, pages or files, so only their type,
    size and first characters are logged."""
    if logger.isEnabledFor(logging.INFO):
        preview = result if isinstance(result, str) else str(result)
        logger.info(
            '%s returned %s: %s',
            label,
            describe_tool_result(result),
            preview[:TOOL_RESULT_PREVIEW_CHARS],
            stacklevel=2,
        )


class ToolExecutionError(AgentError):
    """Error during tool execution"""

    pass


class ToolCallFailed(Exception):
    """The tool ran but could not do what it was called for.

    An agent records the call as failed and gives the model the message as the
    tool's result, without error analysis or retry. Anywhere else, such as a
    function node, it propagates like any other exception.
    """


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        function: Callable,
        parameters: Dict[str, Dict[str, Any]],
    ):
        self.name = name
        self.description = description
        self.function = function

        # Ensure parameters have required field
        self.parameters = {}
        for param_name, param_info in parameters.items():
            self.parameters[param_name] = {
                **param_info,
                'required': param_info.get('required', True),
            }

    async def execute(self, **kwargs) -> Any:
        """Execute the tool with error handling"""
        try:
            logger.info(f'Executing tool {self.name} with kwargs: {kwargs}')
            tool_result = await self.function(**kwargs)
            log_tool_result(f'Tool {self.name}', tool_result)
            return tool_result
        except ToolCallFailed as e:
            logger.warning(f'Tool {self.name} failed: {e}')
            raise
        except Exception as e:
            logger.error(f'Error executing tool {self.name}: {str(e)}', exc_info=True)
            raise ToolExecutionError(
                f'Error executing tool {self.name}: {str(e)}', original_error=e
            )

    async def run(
        self, inputs: List[Any], variables: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Any:
        # Ignore inputs and variables
        # Just pass kwargs to execute()
        return await self.execute(**kwargs)
