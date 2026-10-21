import logging

log_format = (
    '%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s'
)


def configure_flo_utils_logging(log_level: str = 'INFO') -> None:
    """Apply log level from the worker's config.ini at startup."""
    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True,
    )


configure_flo_utils_logging()


class CustomLogger(logging.Logger):
    def error(self, msg, *args, **kwargs):
        """Override the error method to always include exc_info=True."""
        if 'exc_info' not in kwargs:
            kwargs['exc_info'] = True
        super().error(msg, *args, **kwargs)


# Set the custom logger class
logging.setLoggerClass(CustomLogger)
logger = logging.getLogger('Auraflo')
