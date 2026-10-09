import asyncio
import concurrent.futures
import logging
from typing import List, Optional, Sequence, Tuple
from abc import ABC, abstractmethod

from flo_stream.event_message import BaseEventMessage
from flo_stream.message_processor import MessageProcessor, ProcessingResult
from flo_stream.protocols import CacheLike, MessageQueueLike, RawQueueMessage

logger = logging.getLogger(__name__)


class StreamListener(ABC):
    def __init__(
        self,
        event_manager: MessageQueueLike,
        processor: MessageProcessor,
        cache_manager: CacheLike,
        retry_count: int,
        streaming_batch_size: int = 5,
        wait_time_sec: int = 20,
    ):
        self.event_manager = event_manager
        self.processor = processor
        self.cache_manager = cache_manager
        self.retry_count = retry_count
        self.streaming_batch_size = streaming_batch_size
        self.wait_time_sec = wait_time_sec

    def handle_error(
        self,
        message_id: str,
        message_receipt_id: str,
        processor: Optional[MessageProcessor] = None,
        failed_results: Optional[List[ProcessingResult]] = None,
    ):
        """Schedule a retry for a failed message, or give up on it.

        Below retry_count the message stays on the queue to be redelivered.
        Once retries are exhausted, `failed_results` (this message's results,
        success=False) are handed to processor.store(..., is_failed=True) so
        the failure is recorded. The message is removed only once that
        succeeds; if it can't be recorded it stays queued and the next
        delivery tries again. With nothing to record it is removed directly.
        """
        try:
            error_key = f'error_{message_id}'
            current_retry_count = self.cache_manager.get_int(error_key, 0)
            if current_retry_count < self.retry_count:
                self.cache_manager.add(error_key, current_retry_count + 1, expiry=3600)
                # Drop the in-flight marker so the redelivered message is
                # processed again instead of being skipped until it expires.
                self.cache_manager.remove(str(message_id))
                logger.warning(
                    f'Retrying {message_id}. Attempt {current_retry_count} of {self.retry_count}'
                )
                return

            if processor and failed_results:
                if not processor.store(failed_results, is_failed=True):
                    logger.error(
                        f'Max retries exceeded for {message_id} but its failure '
                        'could not be recorded; leaving it on the queue to try again.'
                    )
                    # Keep the retry count so the next delivery comes straight
                    # back here, and let that delivery through the dedup check.
                    self.cache_manager.add(error_key, current_retry_count, expiry=3600)
                    self.cache_manager.remove(str(message_id))
                    return
                logger.error(
                    f'Max retries exceeded for {message_id}; failure recorded. '
                    'Removing from queue.'
                )
            else:
                logger.error(
                    f'Max retries exceeded for {message_id}. Removing from queue.'
                )
            self.delete_message(message_receipt_id)
            self.cache_manager.remove(error_key)
        except Exception as e:
            logger.error(f'Error in error handling: {e}')

    def _failure_results(
        self, message: BaseEventMessage, error: str
    ) -> List[ProcessingResult]:
        """A failed result for `message` from the processor, if it can build one."""
        try:
            result = self.processor.failed_result(message, error)
        except Exception as e:
            logger.error(f'Could not build a failure result for {message.id}: {e}')
            return []
        return [result] if result is not None else []

    def delete_message(self, message_id: str):
        try:
            self.event_manager.delete_message(message_id)
        except Exception as e:
            logger.error(f'Failed to delete message: {e}')

    @abstractmethod
    def get_event_messages(
        self, messages: Sequence[RawQueueMessage]
    ) -> List[BaseEventMessage]:
        pass

    async def receive_queue_messages(self, worker_id: str):
        while True:
            try:
                response = self.event_manager.receive_messages(
                    max_messages=self.streaming_batch_size,
                    wait_time_sec=self.wait_time_sec,
                )
                messages: List[BaseEventMessage] = self.get_event_messages(response)
                logger.info(f'{worker_id}: listening for messages...')
                if not messages:
                    await asyncio.sleep(5)
                    continue

                # (message_id, receipt_id, result) for each message sent to store()
                processed: List[Tuple[str, str, ProcessingResult]] = []
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
                            processed.append(
                                (message_id_str, message_receipt_id, result)
                            )
                        else:
                            self.handle_error(
                                message_id_str,
                                message_receipt_id,
                                self.processor,
                                [result]
                                if result.insights is not None
                                else self._failure_results(
                                    message, result.error or 'Processing failed'
                                ),
                            )

                    except asyncio.TimeoutError:
                        logger.error(
                            f'Task timed out after 5 minutes for message id: {message_id_str}'
                        )
                        self.handle_error(
                            message_id_str,
                            message_receipt_id,
                            self.processor,
                            self._failure_results(
                                message, 'Processing timed out after 5 minutes'
                            ),
                        )
                if insights_to_commit and self.processor:
                    is_successful = self.processor.store(insights_to_commit)
                    if is_successful:
                        # store() may flag individual results as failed
                        # (success=False); those stay on the queue for retry.
                        stored = [p for p in processed if p[2].success]
                        failed = [p for p in processed if not p[2].success]
                        logger.info(
                            f'Successfully stored insights for {len(stored)} items'
                        )
                        for _, message_receipt_id, _ in stored:
                            self.delete_message(message_receipt_id)
                    else:
                        logger.error(
                            f'Failed to store insights for {len(insights_to_commit)} items'
                        )
                        failed = processed
                        for _, _, result in failed:
                            result.success = False
                            result.error = result.error or 'Failed to store insights'
                    for message_id, message_receipt_id, result in failed:
                        logger.error(
                            f'Failed to store insights for message {message_id}: {result.error}'
                        )
                        self.handle_error(
                            message_id,
                            message_receipt_id,
                            self.processor,
                            [result],
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
