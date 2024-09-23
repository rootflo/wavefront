from typing import Any, Dict, List, Union
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema import AgentAction, AgentFinish, LLMResult
from flo_ai.common.flo_logger import get_logger, FloLogConfig
from typing import Optional

class FloLangchainLogger(BaseCallbackHandler):

    def __init__(self, 
                 session_id: str,
                 logger_name: Optional[str] = "FloLangChainLogger", 
                 log_level: Optional[str] = "WARN"):
        self.logger = get_logger(FloLogConfig(logger_name, log_level))
        self.session_id = session_id

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onLLMStart: {prompts}")

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onNewToken: {token}")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onLLMEnd: {response.generations}")

    def on_llm_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any) -> None:
        self.logger.error(f"Session ID: {self.session_id}: onLLMError: {error}")

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onChainStart: {inputs}")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onChainEnd: {outputs}")

    def on_chain_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any) -> None:
        self.logger.error(f"Session ID: {self.session_id}: onChainError: {error}")

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onToolStart: {input_str}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onToolEnd: {output}")

    def on_tool_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs: Any) -> None:
        self.logger.error(f"Session ID: {self.session_id}: onToolError: {error}")

    def on_text(self, text: str, **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onText: {text}")

    def on_agent_action(self, action: AgentAction, **kwargs: Any) -> Any:
        self.logger.debug(f"Session ID: {self.session_id}: onAgentAction: {action.tool} - {action.tool_input}")

    def on_agent_finish(self, finish: AgentFinish, **kwargs: Any) -> None:
        self.logger.debug(f"Session ID: {self.session_id}: onAgentFinish: {finish.return_values}")