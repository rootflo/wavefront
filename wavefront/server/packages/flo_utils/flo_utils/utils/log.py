import os
import logging

log_level = os.environ.get('LOG_LEVEL', 'INFO')
log_format = (
    '%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s'
)
logging.basicConfig(
    level=log_level,
    format=log_format,
    datefmt='%Y-%m-%d %H:%M:%S',
)


class CustomLogger(logging.Logger):
    def error(self, msg, *args, **kwargs):
        """Override the error method to always include exc_info=True."""
        if 'exc_info' not in kwargs:
            kwargs['exc_info'] = True
        super().error(msg, *args, **kwargs)


# Set the custom logger class
logging.setLoggerClass(CustomLogger)
logger = logging.getLogger('Auraflo')
