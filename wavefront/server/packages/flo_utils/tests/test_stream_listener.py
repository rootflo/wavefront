"""
Tests for StreamListener's batch handling: which messages get deleted, which
get retried, and how the retry limit is enforced. The queue, cache and
processor are all in-memory fakes.
"""

from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from flo_utils.streaming.message_processor import MessageProcessor, ProcessingResult
from flo_utils.streaming.stream_listner import StreamListener


class _StopLoop(BaseException):
    """Raised by the fake queue to break out of the listener's endless loop.

    A BaseException so the listener's `except Exception` does not swallow it.
    """


class FakeCache:
    def __init__(self):
        self.data: Dict[str, Any] = {}

    def get_str(self, key: str, default: Any = None) -> Optional[str]:
        return self.data.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self.data.get(key, default))

    def add(self, key: str, value: Any, expiry: int = 3600, nx: bool = False) -> bool:
        self.data[key] = value
        return True

    def remove(self, key: str) -> bool:
        return self.data.pop(key, None) is not None


class FakeProcessor(MessageProcessor):
    """Fails process() for ids in fail_process, marks ids in fail_store as
    failed inside store(), and returns store_result from store()."""

    def __init__(self, fail_process=(), fail_store=(), store_result=True):
        self.fail_process = set(fail_process)
        self.fail_store = set(fail_store)
        self.store_result = store_result
        self.store_calls: List[List[str]] = []

    async def process(self, message) -> ProcessingResult:
        if message.id in self.fail_process:
            return ProcessingResult(success=False, error='process failed')
        return ProcessingResult(success=True, insights={'id': message.id})

    def store(self, insights, **kwargs) -> bool:
        self.store_calls.append([i.insights['id'] for i in insights])
        for insight in insights:
            if insight.insights['id'] in self.fail_store:
                insight.success = False
                insight.error = 'store failed'
        return self.store_result


class FakeListener(StreamListener):
    def get_event_messages(self, messages):
        return messages


def make_messages(*ids: str):
    return [SimpleNamespace(id=i, ack_id=f'ack-{i}') for i in ids]


def make_listener(processor, cache=None, retry_count=3):
    queue = MagicMock()
    listener = FakeListener(queue, processor, cache or FakeCache(), retry_count)
    return listener, queue


async def receive_once(listener, queue, messages):
    """Run a single iteration of the listener loop over `messages`."""
    queue.receive_messages.side_effect = [messages, _StopLoop()]
    with pytest.raises(_StopLoop):
        await listener.receive_queue_messages('worker-test')


def deleted_acks(queue) -> List[str]:
    return [c.args[0] for c in queue.delete_message.call_args_list]


async def test_all_stored_messages_are_deleted():
    processor = FakeProcessor()
    listener, queue = make_listener(processor)

    await receive_once(listener, queue, make_messages('m1', 'm2'))

    assert processor.store_calls == [['m1', 'm2']]
    assert sorted(deleted_acks(queue)) == ['ack-m1', 'ack-m2']


async def test_result_marked_failed_by_store_stays_on_queue():
    cache = FakeCache()
    processor = FakeProcessor(fail_store={'m2'})
    listener, queue = make_listener(processor, cache)

    await receive_once(listener, queue, make_messages('m1', 'm2', 'm3'))

    assert sorted(deleted_acks(queue)) == ['ack-m1', 'ack-m3']
    assert cache.get_int('error_m2') == 1
    assert 'error_m1' not in cache.data and 'error_m3' not in cache.data


async def test_store_returning_false_fails_every_message():
    cache = FakeCache()
    processor = FakeProcessor(store_result=False)
    listener, queue = make_listener(processor, cache)

    await receive_once(listener, queue, make_messages('m1', 'm2', 'm3'))

    queue.delete_message.assert_not_called()
    for message_id in ('m1', 'm2', 'm3'):
        assert cache.get_int(f'error_{message_id}') == 1


async def test_process_failure_does_not_block_rest_of_batch():
    cache = FakeCache()
    processor = FakeProcessor(fail_process={'m1'})
    listener, queue = make_listener(processor, cache)

    await receive_once(listener, queue, make_messages('m1', 'm2'))

    assert processor.store_calls == [['m2']]
    assert deleted_acks(queue) == ['ack-m2']
    assert cache.get_int('error_m1') == 1


async def test_retry_clears_dedup_key_so_redelivery_is_processed():
    cache = FakeCache()
    processor = FakeProcessor(fail_store={'m1'})
    listener, queue = make_listener(processor, cache)

    await receive_once(listener, queue, make_messages('m1'))
    assert 'm1' not in cache.data

    await receive_once(listener, queue, make_messages('m1'))
    assert processor.store_calls == [['m1'], ['m1']]
    assert cache.get_int('error_m1') == 2


async def test_successful_message_redelivery_is_skipped():
    cache = FakeCache()
    processor = FakeProcessor()
    listener, queue = make_listener(processor, cache)

    await receive_once(listener, queue, make_messages('m1'))
    await receive_once(listener, queue, make_messages('m1'))

    assert processor.store_calls == [['m1']]


async def test_message_is_deleted_after_retry_limit():
    cache = FakeCache()
    processor = FakeProcessor(fail_store={'m1'})
    listener, queue = make_listener(processor, cache, retry_count=3)

    for _ in range(3):
        await receive_once(listener, queue, make_messages('m1'))
        queue.delete_message.assert_not_called()

    await receive_once(listener, queue, make_messages('m1'))

    assert deleted_acks(queue) == ['ack-m1']
    assert 'error_m1' not in cache.data
