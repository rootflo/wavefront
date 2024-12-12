import logging
from typing import Any
from typing import Dict, Optional, Union
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass

DEFAULT_LOGGER_NAME = 'FloAI'
DEFAULT_LOG_LEVEL = 'ERROR'

LEVEL_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}


@dataclass
class FloLogConfig:
    name: str
    level: Union[str, int] = DEFAULT_LOG_LEVEL
    file_path: str = None
    max_bytes: int = 1048576

    def get_level(self) -> int:
        """Convert string level to logging level integer if needed"""
        if isinstance(self.level, str):
            return LEVEL_MAP.get(self.level.upper(), logging.ERROR)
        return self.level


class FloLoggerUtil(logging.Logger):
    def __init__(self, config: FloLogConfig):
        level = config.get_level()
        super().__init__(config.name, level)
        self.setLevel(level)
        for handler in self.handlers:
            self.removeHandler(handler)
        self.setConfig(config)

    def setConfig(self, config: FloLogConfig):
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(session)s - %(levelname)s - %(message)s'
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(self.level)
        self.addHandler(console_handler)

        if config.file_path:
            file_handler = RotatingFileHandler(
                config.file_path, maxBytes=config.max_bytes
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(self.level)
            self.addHandler(file_handler)

    def setLevel(self, level: Union[str, int]) -> None:
        if isinstance(level, str):
            level = LEVEL_MAP.get(level.upper(), logging.ERROR)
        super().setLevel(level)
        for handler in self.handlers:
            print('Setting levels in handler: ' + str(level))
            handler.setLevel(level)

    def _log(
        self, level: int, msg: str, session: Optional[Any] = None, *args, **kwargs
    ):
        if not self.isEnabledFor(level):
            return
        if kwargs.get('extra') is None:
            kwargs['extra'] = {}
        kwargs['extra']['session'] = f'[{session.session_id}]' if session else '[-]'
        super()._log(level, msg, args, **kwargs)

    def debug(self, msg: str, session: Optional[Any] = None, *args, **kwargs):
        self._log(logging.DEBUG, msg, session, *args, **kwargs)

    def info(self, msg: str, session: Optional[Any] = None, *args, **kwargs):
        self._log(logging.INFO, msg, session, *args, **kwargs)

    def warning(self, msg: str, session: Optional[Any] = None, *args, **kwargs):
        self._log(logging.WARNING, msg, session, *args, **kwargs)

    def error(self, msg: str, session: Optional[Any] = None, *args, **kwargs):
        self._log(logging.ERROR, msg, session, *args, **kwargs)

    def critical(self, msg: str, session: Optional[Any] = None, *args, **kwargs):
        self._log(logging.CRITICAL, msg, session, *args, **kwargs)


logging_cache: Dict[str, FloLoggerUtil] = dict(
    {
        DEFAULT_LOGGER_NAME: FloLoggerUtil(
            FloLogConfig(DEFAULT_LOGGER_NAME, DEFAULT_LOG_LEVEL)
        )
    }
)


def get_logger(
    config: FloLogConfig = FloLogConfig(DEFAULT_LOGGER_NAME),
) -> FloLoggerUtil:
    if config.name not in logging_cache:
        logging_cache[config.name] = FloLoggerUtil(config)
    return logging_cache[config.name]


def set_log_level_internal(level: Union[str, int]) -> None:
    updated_logger = FloLoggerUtil(FloLogConfig(DEFAULT_LOGGER_NAME, level))
    logging_cache[DEFAULT_LOGGER_NAME] = updated_logger


def set_log_config_internal(config: FloLogConfig):
    updated_logger = FloLoggerUtil(config)
    logging_cache[DEFAULT_LOGGER_NAME] = updated_logger


def set_logger_internal(logger: logging.Logger):
    logging_cache[DEFAULT_LOGGER_NAME] = logger
