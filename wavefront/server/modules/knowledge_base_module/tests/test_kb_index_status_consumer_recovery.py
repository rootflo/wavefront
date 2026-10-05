"""
Recovery of index status events that were delivered but never acknowledged:
replay of this consumer's own pending entries on startup, reclaiming idle
entries from any consumer, and dropping entries after too many deliveries.
Redis is a fake that keeps a real pending-entries list.
"""

from unittest.mock import AsyncMock, MagicMock

from knowledge_base_module.services import kb_index_status_consumer as module
from knowledge_base_module.services.kb_index_status_consumer import (
    KbIndexStatusConsumer,
)

ME = module._CONSUMER
OTHER = 'floware-dead-replica'
IDLE = module._RECLAIM_MIN_IDLE_MS


def _key(msg_id: str):
    ms, _, seq = msg_id.partition('-')
    return int(ms), int(seq or 0)


class FakeStream:
    """A stream with one consumer group's pending-entries list (PEL)."""

    def __init__(self):
        self.namespace = 'floware'
        self.entries = {}  # id -> fields (None once trimmed)
        self.pel = {}  # id -> {'consumer', 'times_delivered', 'idle'}
        self.acked = []

    def add_pending(self, msg_id, consumer, fields=None, times=1, idle=0):
        self.entries[msg_id] = fields if fields is not None else {'doc_id': msg_id}
        self.pel[msg_id] = {
            'consumer': consumer,
            'times_delivered': times,
            'idle': idle,
        }

    # --- the CacheManager calls the consumer makes ---------------------------

    def xgroup_create(self, *args, **kwargs):
        pass

    def xread_group(self, group, consumer, streams, count, block_ms):
        [cursor] = streams.values()
        if cursor == '>':
            return []  # no new entries in these tests
        own = sorted(
            (
                i
                for i, p in self.pel.items()
                if p['consumer'] == consumer and _key(i) > _key(cursor)
            ),
            key=_key,
        )[:count]
        return [('stream', [(i, self.entries.get(i)) for i in own])] if own else []

    def xack(self, stream, group, *msg_ids):
        for msg_id in msg_ids:
            if self.pel.pop(msg_id, None) is not None:
                self.acked.append(msg_id)
        return len(msg_ids)

    def xpending_range(
        self, stream, group, count, min_idle_ms=None, consumer=None, start='-', end='+'
    ):
        rows = [
            {
                'message_id': i,
                'consumer': p['consumer'],
                'times_delivered': p['times_delivered'],
            }
            for i, p in sorted(self.pel.items(), key=lambda kv: _key(kv[0]))
            if (consumer is None or p['consumer'] == consumer)
            and (min_idle_ms is None or p['idle'] >= min_idle_ms)
            and (start == '-' or _key(i) >= _key(start))
        ]
        return rows[:count]

    def xautoclaim(
        self, stream, group, consumer, min_idle_ms, start_id='0-0', count=None
    ):
        claimed = []
        for msg_id, p in sorted(self.pel.items(), key=lambda kv: _key(kv[0])):
            if p['idle'] >= min_idle_ms:
                p.update(
                    consumer=consumer, idle=0, times_delivered=p['times_delivered'] + 1
                )
                claimed.append((msg_id, self.entries.get(msg_id)))
        return claimed[:count] if count else claimed


def make_consumer(stream, failing=()):
    consumer = KbIndexStatusConsumer(documents_repo=MagicMock(), cache_manager=stream)
    consumer._running = True

    async def process(fields):
        if fields['doc_id'] in failing:
            raise RuntimeError('database unavailable')
        return True

    consumer.process = AsyncMock(side_effect=process)
    return consumer


def processed(consumer):
    return [c.args[0]['doc_id'] for c in consumer.process.await_args_list]


# --- replaying own pending entries on startup ---------------------------------


async def test_startup_replays_own_pending_entries():
    stream = FakeStream()
    stream.add_pending('1-0', ME)
    stream.add_pending('2-0', ME)
    stream.add_pending('3-0', OTHER)  # another replica's: left to reclaim
    consumer = make_consumer(stream, failing={'2-0'})

    await consumer._drain_own_pending()

    assert processed(consumer) == ['1-0', '2-0']  # each tried once, no loop
    assert stream.acked == ['1-0']
    assert set(stream.pel) == {'2-0', '3-0'}


async def test_startup_replay_pages_through_many_entries(monkeypatch):
    monkeypatch.setattr(module, '_POLL_COUNT', 2)
    stream = FakeStream()
    for i in range(1, 6):
        stream.add_pending(f'{i}-0', ME)
    consumer = make_consumer(stream)

    await consumer._drain_own_pending()

    assert stream.acked == ['1-0', '2-0', '3-0', '4-0', '5-0']


async def test_startup_drops_own_entries_out_of_deliveries():
    stream = FakeStream()
    stream.add_pending('1-0', ME, times=module._MAX_DELIVERIES)
    stream.add_pending('2-0', ME)
    consumer = make_consumer(stream)

    await consumer._drain_own_pending()

    assert processed(consumer) == ['2-0']
    assert sorted(stream.acked) == ['1-0', '2-0']


async def test_trimmed_entries_are_acknowledged_without_processing():
    stream = FakeStream()
    stream.add_pending('1-0', ME)
    stream.entries['1-0'] = None  # trimmed from the stream while pending
    consumer = make_consumer(stream)

    await consumer._drain_own_pending()

    assert processed(consumer) == []
    assert stream.acked == ['1-0']


# --- reclaiming idle entries ----------------------------------------------------


async def test_idle_entries_from_a_dead_replica_are_reclaimed_and_applied():
    stream = FakeStream()
    stream.add_pending('1-0', OTHER, idle=IDLE)
    stream.add_pending('2-0', OTHER, idle=IDLE - 1)  # still in flight elsewhere
    consumer = make_consumer(stream)

    await consumer._reclaim_idle()

    assert processed(consumer) == ['1-0']
    assert stream.acked == ['1-0']
    assert stream.pel['2-0']['consumer'] == OTHER


async def test_failed_reclaimed_entry_stays_pending_for_another_attempt():
    stream = FakeStream()
    stream.add_pending('1-0', ME, idle=IDLE)
    consumer = make_consumer(stream, failing={'1-0'})

    await consumer._reclaim_idle()

    assert stream.acked == []
    assert stream.pel['1-0']['times_delivered'] == 2


async def test_entry_that_keeps_failing_is_dropped_after_max_deliveries():
    stream = FakeStream()
    stream.add_pending('1-0', ME, idle=IDLE)
    consumer = make_consumer(stream, failing={'1-0'})

    for _ in range(module._MAX_DELIVERIES + 2):
        await consumer._reclaim_idle()
        if '1-0' in stream.pel:
            stream.pel['1-0']['idle'] = IDLE  # time passes

    assert '1-0' not in stream.pel
    assert stream.acked == ['1-0']
    # delivered once originally, then retried until the cap
    assert consumer.process.await_count == module._MAX_DELIVERIES - 1


async def test_reclaim_errors_are_logged_not_raised():
    stream = FakeStream()
    stream.xpending_range = MagicMock(side_effect=ConnectionError('redis down'))
    consumer = make_consumer(stream)

    await consumer._reclaim_idle()  # must not raise

    consumer.process.assert_not_awaited()


# --- wired into the loop ------------------------------------------------------------


async def test_loop_replays_pending_then_reclaims_on_schedule(monkeypatch):
    monkeypatch.setattr(module, '_RECLAIM_INTERVAL_S', 0)
    monkeypatch.setattr(module, '_POLL_INTERVAL_S', 0)
    stream = FakeStream()
    stream.add_pending('1-0', ME)  # from before a restart
    stream.add_pending('2-0', OTHER, idle=IDLE)  # stranded on a dead replica
    consumer = make_consumer(stream)
    consumer._sleep = AsyncMock(side_effect=lambda _s: consumer.stop())

    await consumer.start()

    assert processed(consumer) == ['1-0', '2-0']
    assert stream.acked == ['1-0', '2-0']
