import logging


class RequestAwareFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return super().format(record)


class RequestAwareLogger(logging.Logger):
    def error(self, msg, *args, **kwargs):
        """Override error method to always include exc_info=True."""
        if 'exc_info' not in kwargs:
            kwargs['exc_info'] = True
        super().error(msg, *args, **kwargs)


log_format = (
    '%(asctime)s | %(levelname)-8s | %(name)s | '
    '%(filename)s:%(lineno)d | %(message)s'
)

formatter = RequestAwareFormatter(fmt=log_format, datefmt='%Y-%m-%d %H:%M:%S')

logging.setLoggerClass(RequestAwareLogger)


def configure_logging(log_level: str = 'INFO') -> None:
    logging.getLogger('uvicorn').setLevel(log_level)
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True,
    )
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)


logger = logging.getLogger('call_processing')
