import asyncio
import threading
from db_repo_module.cache.cache_manager import CacheManager
from common_module.log.logger import logger
from api_services_module.utils.api_change_processor import ApiChangeProcessor
from api_services_module.utils.api_change_publisher import (
    REDIS_API_SERVICE_UPDATES_CHANNEL,
)


async def start_redis_listener(
    cache_manager: CacheManager,
    api_change_processor: ApiChangeProcessor,
):
    """
    Start Redis PubSub listener in a non-blocking way.
    """
    queue = asyncio.Queue()

    pubsub = cache_manager.subscribe(channels=[REDIS_API_SERVICE_UPDATES_CHANNEL])
    logger.info('Subscribed to Redis channel: %s', REDIS_API_SERVICE_UPDATES_CHANNEL)

    # Capture the running loop from the main thread
    loop = asyncio.get_running_loop()

    # Run the blocking pubsub.listen() inside a thread
    def run_pubsub():
        try:
            for message in pubsub.listen():
                if message['type'] == 'message':
                    asyncio.run_coroutine_threadsafe(queue.put(message['data']), loop)
        except Exception as e:
            logger.error(f'Error in pubsub thread: {e}')

    thread = threading.Thread(target=run_pubsub, daemon=True)
    thread.start()

    logger.info('Redis listener thread started')

    # Async loop: process messages from the queue
    while True:
        data = await queue.get()
        try:
            logger.info(f'Received update: {data}')
            await api_change_processor.process_message(data)
        except Exception as e:
            logger.error(f'Error processing message: {e}')
        finally:
            queue.task_done()
