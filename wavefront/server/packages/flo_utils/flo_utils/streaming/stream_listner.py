import asyncio
import concurrent.futures
from typing import List
from flo_cloud._types import MessageQueueDict
from common_module.log.logger import logger
from db_repo_module.cache.cache_manager import CacheManager
from flo_cloud._types import MessageQueue

from abc import ABC, abstractmethod
from flo_utils.streaming.event_message import BaseEventMessage
from flo_utils.streaming.message_processor import MessageProcessor, ProcessingResult


class StreamListener(ABC):
    def __init__(
        self,
        event_manager: MessageQueue,
        processor: MessageProcessor,
        cache_manager: CacheManager,
        retry_count: int,
        streaming_batch_size: int = 5,
    ):
        self.event_manager = event_manager
        self.processor = processor
        self.cache_manager = cache_manager
        self.retry_count = retry_count
        self.streaming_batch_size = streaming_batch_size

    def handle_error(
        self,
        message_id: str,
        message_receipt_id: str,
        processor: MessageProcessor = None,
        insights_to_commit: List = [],
    ):
        try:
            error_key = f'error_{message_id}'
            current_retry_count = self.cache_manager.get_int(error_key, 0)
            if current_retry_count >= self.retry_count:
                logger.error(
                    f'Max retries exceeded for {message_id}. Removing from queue.'
                )
                self.delete_message(message_receipt_id)
                if processor and len(insights_to_commit) > 0:
                    logger.error(
                        f'Storing failed insights for {message_id} after max retries.'
                    )
                    processor.store(insights_to_commit, as_failed=True)
                self.cache_manager.remove(error_key)
            else:
                self.cache_manager.add(error_key, current_retry_count + 1, expiry=3600)
                logger.warning(
                    f'Retrying {message_id}. Attempt {current_retry_count} of {self.retry_count}'
                )
        except Exception as e:
            logger.error(f'Error in error handling: {e}')

    def delete_message(self, message_id: str):
        try:
            self.event_manager.delete_message(message_id)
        except Exception as e:
            logger.error(f'Failed to delete message: {e}')

    @abstractmethod
    def get_event_messages(
        self, messages: List[MessageQueueDict]
    ) -> List[BaseEventMessage]:
        pass

    async def receive_queue_messages(self, worker_id: str):
        while True:
            try:
                response = self.event_manager.receive_messages(
                    max_messages=self.streaming_batch_size
                )
                messages: List[BaseEventMessage] = self.get_event_messages(response)
                logger.info(f'{worker_id}: listening for messages...')
                if not messages:
                    await asyncio.sleep(5)
                    continue

                message_ids_to_delete = []
                insights_to_commit: List[ProcessingResult] = []

                for message in messages:
                    message_receipt_id = message.ack_id
                    message_id_str = message.id

                    if self.cache_manager.get_str(str(message_id_str)):
                        continue

                    self.cache_manager.add(str(message_id_str), '1')
                    try:
                        result: ProcessingResult = await asyncio.wait_for(
                            self.processor.process(message), timeout=60 * 5
                        )

                        if result.success:
                            insights_to_commit.append(result)
                            message_ids_to_delete.append(message_receipt_id)
                        else:
                            self.handle_error(message_id_str, message_receipt_id)

                    except asyncio.TimeoutError:
                        logger.error(
                            f'Task timed out after 5 minutes for message id: {message_id_str}'
                        )
                        self.handle_error(
                            message_id_str,
                            message_receipt_id,
                            self.processor,
                            insights_to_commit,
                        )
                if insights_to_commit and self.processor:
                    is_successful = self.processor.store(insights_to_commit)
                    if is_successful:
                        logger.info(
                            f'Successfully stored insights for {len(insights_to_commit)} items'
                        )
                        for message_receipt_id in message_ids_to_delete:
                            self.delete_message(message_receipt_id)
                    else:
                        logger.error(
                            f'Failed to store insights for {len(insights_to_commit)} items'
                        )
                        self.handle_error(
                            message_id_str,
                            message_receipt_id,
                            self.processor,
                            insights_to_commit,
                        )
            except Exception as e:
                logger.error(
                    f'Unexpected error in message processing: {e}', exc_info=True
                )
                await asyncio.sleep(10)

    def run_workers(self, thread_count: int):
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=thread_count
        ) as executor:
            futures = [
                executor.submit(self._run_worker, f'Worker {i+1}')
                for i in range(thread_count)
            ]
            concurrent.futures.wait(futures)

        logger.warning('All workers have stopped')

    def _run_worker(self, worker_id: str):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.receive_queue_messages(worker_id))
        except Exception as e:
            logger.error(f'Worker {worker_id} crashed: {e}')
        finally:
            loop.close()
