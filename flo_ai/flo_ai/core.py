import asyncio
import warnings
import logging
from typing import Optional
from langchain_core.runnables import Runnable
from flo_ai.yaml.config import to_supervised_team
from flo_ai.builders.yaml_builder import build_supervised_team
from typing import Any, Iterator, Union
from flo_ai.router.flo_router import FloRouter
from flo_ai.state.flo_session import FloSession
from flo_ai.models.flo_llm_agent import FloLLMAgent
from flo_ai.models.flo_executable import ExecutableFlo
from flo_ai.error.flo_exception import FloException
from flo_ai.constants.common_constants import DOCUMENTATION_WEBSITE
from flo_ai.common.flo_logger import (
    get_logger,
    set_log_level_internal,
    set_log_config_internal,
    set_logger_internal,
    FloLogConfig,
)
from langchain_core.messages import BaseMessage
from flo_ai.models.flo_node import FloNode
from flo_ai.models.flo_agent import FloAgent
from langchain.tools import StructuredTool
from flo_ai.callbacks.flo_execution_logger import ToolLogger


class Flo:
    def __init__(self, session: FloSession, executable: Runnable) -> None:
        self.session = session
        self.runnable: ExecutableFlo = executable

        self.langchain_logger = session.langchain_logger
        get_logger().info('Flo instance created ...', session)

    def stream(self, query, config=None) -> Iterator[Union[dict[str, Any], Any]]:
        self.validate_invoke(self.session)
        get_logger().info(f"streaming query requested: '{query}'", self.session)
        return self.runnable.stream(query, config)

    def async_stream(self, query, config=None) -> Iterator[Union[dict[str, Any], Any]]:
        get_logger().info(f"Streaming async query requested: '{query}'", self.session)
        return self.runnable.astream(query, config)

    def invoke(
        self, query, config=None, chat_history: list[BaseMessage] = []
    ) -> Iterator[Union[dict[str, Any], Any]]:
        config = self.session.prepare_config(config)

        for callback in self.session.callbacks:
            if isinstance(callback, ToolLogger):
                callback.log_all_tools(self.session.tools)

        self.validate_invoke(self.session)
        get_logger().info(f"Invoking query: '{query}'", self.session)
        return self.runnable.invoke(query, config, chat_history)

    def async_invoke(
        self, query, config=None, chat_history: list[BaseMessage] = []
    ) -> Iterator[Union[dict[str, Any], Any]]:
        get_logger().info(f"Invoking async query: '{query}'", self.session)
        return self.runnable.ainvoke(query, config, chat_history)

    @staticmethod
    def build(
        session: FloSession,
        yaml: Optional[str] = None,
        yaml_path: Optional[str] = None,
        routed_team: Optional[FloRouter] = None,
        log_level: Optional[str] = None,
    ):
        if log_level:
            warnings.warn(
                '`log_level` is deprecated and will be removed in a future version. '
                'Please use `Flo.set_log_level()` instead.',
                DeprecationWarning,
                stacklevel=2,
            )
            Flo.set_log_level(log_level)
        if yaml_path:
            if yaml is not None:
                raise FloException(
                    'Cannot specify both `yaml` and `yaml_path`. Use only one.'
                )
            try:
                with open(yaml_path) as file:
                    yaml = file.read()
            except FileNotFoundError:
                raise FloException(f'YAML file at path {yaml_path} not found.')
            except Exception:
                raise FloException(f'Error reading YAML file at path {yaml_path}.')

        if yaml is not None:
            get_logger().info('Building Flo instance from YAML ...', session)
            executable: ExecutableFlo = build_supervised_team(
                session, to_supervised_team(yaml)
            )
            # TODO fix this for all agents later
            if isinstance(executable, FloAgent) or isinstance(executable, FloLLMAgent):
                executable = FloNode.Builder(session).build_from_agent(executable)
            return Flo(session, executable)
        if routed_team is not None:
            return Flo(session, routed_team.build_routed_team())
        raise FloException("""Either yaml or routed_team should be not None""")

    @staticmethod
    def create(session: FloSession, routed_team: Union[FloRouter, FloAgent]):
        if isinstance(routed_team, FloRouter):
            runnable = routed_team.build_routed_team()
        else:
            runnable = FloNode.Builder(session).build_from_agent(routed_team)
        return Flo(session, runnable)

    @staticmethod
    def set_log_level(log_level: str):
        set_log_level_internal(log_level)

    @staticmethod
    def set_log_config(logging_config: FloLogConfig):
        set_log_config_internal(logging_config)

    @staticmethod
    def set_logger(logging_config: logging.Logger):
        set_logger_internal(logging_config)

    def draw(self, xray=True):
        from IPython.display import Image, display

        image = self.runnable.draw(xray)
        return display(Image(self.runnable.draw(xray))) if image is not None else None

    def draw_to_file(self, filename: str, xray=True):
        from PIL import Image as PILImage
        import io

        byte_image = self.runnable.draw(xray)
        with io.BytesIO(byte_image) as image_io:
            image = PILImage.open(image_io)
            image.save(filename)

    def validate_invoke(self, session: FloSession):
        async_coroutines = filter(
            lambda x: (
                isinstance(x, StructuredTool)
                and hasattr(x, 'coroutine')
                and asyncio.iscoroutinefunction(x.coroutine)
            ),
            session.tools.values(),
        )
        async_tools = list(async_coroutines)
        if len(async_tools) > 0:
            raise FloException(
                f"""You seem to have atleast one async tool registered in this session. Please use flo.async_invoke or flo.async_stream. Checkout {DOCUMENTATION_WEBSITE}"""
            )
