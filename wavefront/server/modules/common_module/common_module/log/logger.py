import logging

from ..middleware.request_id_middleware import get_current_request_id


class RequestAwareFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        request_id = get_current_request_id()
        record.request_id = request_id
        return super().format(record)


class RequestAwareLogger(logging.Logger):
    def error(self, msg, *args, **kwargs):
        """Override error method to always include exc_info=True."""
        if 'exc_info' not in kwargs:
            kwargs['exc_info'] = True
        super().error(msg, *args, **kwargs)


log_format = (
    '%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | '
    '%(filename)s:%(lineno)d | %(message)s'
)

formatter = RequestAwareFormatter(fmt=log_format, datefmt='%Y-%m-%d %H:%M:%S')

logging.setLoggerClass(RequestAwareLogger)


def configure_logging(app_name: str = 'floware', log_level: str = 'INFO') -> None:
    """Apply logging settings from the app's config.ini at startup.

    Configures the root logger and the named app logger. Callers keep the
    ``logger`` object they imported; rebinding this module global would not
    reach them.
    """
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
    logging.getLogger(app_name).setLevel(log_level)


logger = logging.getLogger('floware')
