import logging
import os


class RequestAwareFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return super().format(record)


class RequestAwareLogger(logging.Logger):
    def error(self, msg, *args, **kwargs):
        """Override error method to always include exc_info=True."""
        if 'exc_info' not in kwargs:
            kwargs['exc_info'] = True
        super().error(msg, *args, **kwargs)


log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.getLogger('uvicorn').setLevel(log_level)

log_format = (
    '%(asctime)s | %(levelname)-8s | %(name)s | '
    '%(filename)s:%(lineno)d | %(message)s'
)

formatter = RequestAwareFormatter(fmt=log_format, datefmt='%Y-%m-%d %H:%M:%S')

logging.setLoggerClass(RequestAwareLogger)

logging.basicConfig(
    level=log_level,
    format=log_format,
    datefmt='%Y-%m-%d %H:%M:%S',
    force=True,  # Override any existing configuration
)

# Get root logger and apply custom formatter
root_logger = logging.getLogger()
for handler in root_logger.handlers:
    handler.setFormatter(formatter)

logger = logging.getLogger('call_processing')
