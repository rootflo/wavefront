import logging
import os

log_level = os.environ.get('FLO_AI_LOG_LEVEL', 'INFO')
log_format = (
    '%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s'
)

logger = logging.getLogger('flo_ai')
logger.setLevel(log_level)

# Prevent affecting the root logger
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Optional: stop logs from propagating to the root logger
logger.propagate = False
