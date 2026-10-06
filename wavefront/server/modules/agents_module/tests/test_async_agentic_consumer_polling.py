"""
Polling behaviour of AsyncAgenticExecutionResultConsumer: non-blocking reads, a pause
between polls that come back short, immediate re-reads while a backlog
drains, and a prompt stop. Redis is a fake; applying events is stubbed.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from agents_module.services import async_agentic_execution_result_consumer as module
from agents_module.services.async_agentic_execution_result_consumer import (
    AsyncAgenticExecutionResultConsumer,
)

STREAM = 'async_agentic_exec:results'


class ScriptedCache:
    """Answers xread_group from `batches` (sizes), then stops the consumer."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.namespace = 'floware'
        self.consumer = None
        self.block_args = []
        self.read_times = []
        self.acked = []

    def xgroup_create(self, *args, **kwargs):
        pass

    def xread_group(self, group, consumer, streams, count, block_ms):
        self.block_args.append(block_ms)
        self.read_times.append(time.monotonic())
        if not self.batches:
            self.consumer.stop()
            return []
        size = self.batches.pop(0)
        if isinstance(size, Exception):
            raise size
        return (
            [(STREAM, [(f'{i}-0', {'n': str(i)}) for i in range(size)])] if size else []
        )

    def xack(self, stream, group, msg_id):
        self.acked.append(msg_id)


def make_consumer(batches, *, poll_interval_s: float = 0.01):
    cache = ScriptedCache(batches)
    consumer = AsyncAgenticExecutionResultConsumer(
        exec_repo=MagicMock(),
        cache_manager=cache,
        poll_interval_s=poll_interval_s,
    )
    cache.consumer = consumer
    consumer._process = AsyncMock(return_value=None)
    consumer._sleep = AsyncMock(wraps=consumer._sleep)
    return consumer, cache


async def run(consumer):
    await asyncio.wait_for(consumer.start(), timeout=5)


async def test_reads_do_not_block_on_redis():
    consumer, cache = make_consumer([0, 3])

    await run(consumer)

    assert cache.block_args and all(block is None for block in cache.block_args)


async def test_sleeps_after_a_short_batch():
    consumer, cache = make_consumer([0, 2])

    await run(consumer)

    # one sleep per short read (the empty one and the 2-message one); none
    # after the final read, during which stop() is called
    assert [c.args[0] for c in consumer._sleep.await_args_list] == [0.01, 0.01]


async def test_full_batch_is_followed_by_an_immediate_read():
    full = module._POLL_COUNT
    consumer, cache = make_consumer([full, full, 1])

    await run(consumer)

    # only the short batch sleeps; the two full ones are re-read at once
    assert consumer._sleep.await_count == 1
    assert consumer._process.await_count == 2 * full + 1
    assert len(cache.acked) == 2 * full + 1


async def test_poll_error_backs_off_at_least_two_seconds(monkeypatch):
    consumer, cache = make_consumer([ConnectionError('redis down')])
    consumer._sleep = AsyncMock()

    await run(consumer)

    consumer._sleep.assert_awaited_once_with(2)


async def test_stop_interrupts_the_sleep_between_polls():
    cache = MagicMock(namespace='floware')
    cache.xread_group.return_value = []
    consumer = AsyncAgenticExecutionResultConsumer(
        exec_repo=MagicMock(),
        cache_manager=cache,
        poll_interval_s=30,
    )

    task = asyncio.create_task(consumer.start())
    while cache.xread_group.call_count == 0:
        await asyncio.sleep(0.01)
    started = time.monotonic()
    consumer.stop()
    await asyncio.wait_for(task, timeout=2)

    assert time.monotonic() - started < 1
    assert cache.xread_group.call_count == 1
