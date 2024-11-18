from typing import Any, Dict, List, Union
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
from flo_ai.common.flo_logger import get_logger
from flo_ai.callbacks.flo_callbacks import FloToolCallback


class FloLangchainLogger(BaseCallbackHandler):
    def __init__(self, session_id: str, tool_callbacks: List[FloToolCallback] = []):
        self.session_id = session_id
        self.tool_callbacks = tool_callbacks

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        get_logger().debug(f'onLLMStart: {prompts}', self)

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        get_logger().debug(f'onNewToken: {token}', self)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        get_logger().debug(f'onLLMEnd: {response.generations}', self)

    def on_llm_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        get_logger().debug(f'onLLMEnd: {error}', self)

    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> None:
        get_logger().debug(f'onChainStart: {inputs}', self)

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        get_logger().debug(f'onChainEnd: {outputs}', self)

    def on_chain_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        get_logger().debug(f'onChainError: {error}', self)

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        get_logger().debug(f'onToolStart: {input_str}', self)
        [
            x.on_tool_start(serialized['name'], kwargs['inputs'], kwargs)
            for x in self.tool_callbacks
        ]

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        get_logger().debug(f'onToolEnd: {output}', self)
        [x.on_tool_end(kwargs['name'], output, kwargs) for x in self.tool_callbacks]

    def on_tool_error(
        self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any
    ) -> None:
        get_logger().debug(f'onToolError: {error}', self)
        [x.on_tool_error(kwargs['name'], error, kwargs) for x in self.tool_callbacks]

    def on_text(self, text: str, **kwargs: Any) -> None:
        get_logger().debug(f'onText: {text}', self)

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        get_logger().debug(f'onAgentAction: {action.tool} - {action.tool_input}', self)

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        get_logger().debug(f'onAgentFinish: {finish.return_values}', self)
