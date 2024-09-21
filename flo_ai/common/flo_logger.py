import os
import logging
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass

@dataclass
class FloLogConfig:
    name: str
    level: str = "INFO"
    file_path: str = None
    max_bytes: int = 1048576

class FloLoggerUtil(logging.Logger):
    def __init__(self, config: FloLogConfig):
        super().__init__(config.name, config.level)
        self.setLevel(config.level)

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)

        if config.file_path:
            file_handler = RotatingFileHandler(config.file_path, maxBytes=config.max_bytes)
            file_handler.setFormatter(formatter)
            self.addHandler(file_handler)

class FloLogger:
    _loggers = {}

    @classmethod
    def get_logger(cls, config: FloLogConfig) -> FloLoggerUtil:
        if config.name not in cls._loggers:
            level = config.level or os.environ.get(f"FLO_LOG_LEVEL_{config.name.upper()}", "INFO")
            config.level = level
            cls._loggers[config.name] = FloLoggerUtil(config)
        return cls._loggers[config.name]

    @classmethod
    def set_log_level(cls, name: str, level: str):
        if name in cls._loggers:
            cls._loggers[name].setLevel(level)

def get_logger(config: FloLogConfig) -> FloLoggerUtil:
    return FloLogger.get_logger(config)

common_logger = get_logger(FloLogConfig("COMMON"))
builder_logger = get_logger(FloLogConfig("BUILDER"))
session_logger = get_logger(FloLogConfig("SESSION"))

def set_global_log_level(level: str):
    for name in ["COMMON", "BUILDER", "SESSION"]:
        FloLogger.set_log_level(name, level)