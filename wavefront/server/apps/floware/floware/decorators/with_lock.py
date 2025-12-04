from functools import wraps

from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from pottery import Redlock


def with_lock(
    lock_key: str, cache_manager: CacheManager, auto_release_time=600, cache_expiry=3600
):
    """
    Decorator to handle distributed locking using Redlock.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            lock = Redlock(
                key=lock_key,
                masters={cache_manager.redis},
                auto_release_time=auto_release_time,
            )
            try:
                with lock:
                    if cache_manager.get_str(lock_key):
                        logger.info(
                            f'Job "{lock_key}" already executed. Skipping re-run.'
                        )
                        return
                    # Execute the wrapped function
                    if cache_manager.add(lock_key, 1, expiry=cache_expiry):
                        logger.info(f'Executing the job "{lock_key}"')
                    result = func(*args, **kwargs)
                    return result
            except Exception as e:
                logger.error(f'Error while executing job "{e}"')
                raise

        return wrapper

    return decorator
