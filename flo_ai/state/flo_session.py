import uuid
from typing import Union
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import BaseTool
from flo_ai.common.flo_logger import session_logger, FloLogger
from flo_ai.common.flo_langchain_logger import FloLangchainLogger
from flo_ai.yaml.config import FloRoutedTeamConfig, FloAgentConfig
from flo_ai.helpers.utils import random_str

from typing import Optional

class FloSession:

    def __init__(self, 
                 llm: BaseLanguageModel, 
                 loop_size: int = 2, 
                 max_loop: int = 3, 
                 log_level: Optional[str] = "INFO",
                 custom_langchainlog_handler: Optional[FloLangchainLogger] = None) -> None:
        
        self.session_id = str(random_str(16))
        self.llm = llm
        self.tools = dict()
        self.counter = dict()
        self.navigation: list[str] = list()
        self.pattern_series = dict()
        self.loop_size: int = loop_size
        self.max_loop: int = max_loop
        
        self.init_logger(log_level)
        self.logger = session_logger
        self.config: Union[FloRoutedTeamConfig, FloAgentConfig] = None
        self.logger.info(f"New FloSession created with ID: {self.session_id}")
        self.langchain_logger = custom_langchainlog_handler or FloLangchainLogger(self.session_id, log_level=log_level, logger_name=f"FloLangChainLogger-{self.session_id}")

    def init_logger(self, log_level: str):
        FloLogger.set_log_level("SESSION", log_level)

    def register_tool(self, name: str, tool: BaseTool):
        self.tools[name] = tool
        self.logger.info(f"Tool '{name}' registered for session {self.session_id}")
        return self

    def append(self, node: str) -> int:
        self.logger.debug(f"Appending node: {node}")
        self.counter[node] = self.counter.get(node, 0) + 1
        if node in self.navigation:
            last_known_index = len(self.navigation) - 1 - self.navigation[::-1].index(node)
            pattern_array = self.navigation[last_known_index: len(self.navigation)]
            if len(pattern_array) + 1 >= self.loop_size:
                pattern = "|".join(pattern_array) + "|" + node
                if node in self.pattern_series:
                    self.pattern_series[node].append(pattern)
                else:
                    self.pattern_series[node] = [pattern]
        self.navigation.append(node)

    def is_looping(self, node) -> bool:
        self.logger.debug(f"Checking if node {node} is looping")
        patterns = self.pattern_series[node] if node in self.pattern_series else []
        if len(patterns) < self.max_loop:
            return False
        return patterns[-(self.max_loop):] == [patterns[-1]] * self.max_loop

    def stringify(self):
        return str(self.counter)