"""Queue-depth gate for the Celery broker. The kombu channel is faked."""

import threading
from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest
from celery import Celery

from agents_module.utils import celery_backpressure as bp
from agents_module.utils.celery_backpressure import QueueBackpressure
from agents_module.utils.celery_settings import CeleryProducerSettings

# The real class a kombu ConnectionPool raises, without importing kombu.
POOL_LIMIT_EXCEEDED = Celery('probe-test', set_as_current=False).pool.LimitExceeded

# Shape of kombu's queue_declare_ok_t.
declare_ok = namedtuple(
    'queue_declare_ok_t', ('queue', 'message_count', 'consumer_count')
)

APP = MagicMock(name='celery_app')


class _Knobs:
    """Settings the gate is called with in the current test."""

    def __init__(self):
        self._values = {}

    def reset(self):
        self._values = {}

    def set(self, **values):
        self._values.update(values)

    @property
    def settings(self):
        return CeleryProducerSettings(**self._values)


KNOBS = _Knobs()


@pytest.fixture(autouse=True)
def reset_gate():
    """Each test starts with no reading, unthrottled logs and default knobs."""
    bp._reset_for_tests()
    KNOBS.reset()
    yield
    bp._reset_for_tests()
    KNOBS.reset()


@pytest.fixture
def limit_10(monkeypatch):
    KNOBS.set(max_queue_depth=10)
    return 10


def fake_app(depth):
    """A Celery app stand-in whose channel reports `depth` ready messages."""
    app = MagicMock()
    app.conf.task_default_queue = '{celery}'
    channel = app.pool.acquire.return_value.default_channel
    channel.queue_declare.return_value = declare_ok('{celery}', depth, 0)
    return app, channel


# --- measurement ----------------------------------------------------------


def test_measures_depth_through_queue_declare():
    app, channel = fake_app(7)

    assert bp.measure_queue_depth(app, KNOBS.settings) == 7


def test_declares_the_hash_tagged_queue_non_passively():
    """The key is literally `{celery}`; passive=True raises on an empty queue."""
    app, channel = fake_app(0)

    bp.measure_queue_depth(app, KNOBS.settings)

    channel.queue_declare.assert_called_once_with(queue='{celery}')
    assert 'passive' not in channel.queue_declare.call_args.kwargs


def test_measures_the_queue_the_client_publishes_to():
    from agents_module.utils.celery_client import build_celery_client

    real = build_celery_client('redis://localhost:6379/0', 'app2')
    app, channel = fake_app(0)
    app.conf.task_default_queue = real.conf.task_default_queue

    bp.measure_queue_depth(app, KNOBS.settings)

    channel.queue_declare.assert_called_once_with(queue='{app2}')


def test_acquires_with_a_timeout_and_releases():
    """An unbounded acquire could park the probe behind publishes."""
    app, _channel = fake_app(0)

    bp.measure_queue_depth(app, KNOBS.settings)

    assert app.pool.acquire.call_args.kwargs['block'] is True
    assert app.pool.acquire.call_args.kwargs['timeout'] > 0
    app.pool.acquire.return_value.release.assert_called_once()


def test_connection_is_released_even_when_the_probe_raises():
    app, channel = fake_app(0)
    channel.queue_declare.side_effect = OSError('broker down')

    with pytest.raises(OSError):
        bp.measure_queue_depth(app, KNOBS.settings)

    app.pool.acquire.return_value.release.assert_called_once()


def test_probe_makes_a_single_connection_attempt():
    """kombu otherwise retries the connect for ~6s."""
    app, _channel = fake_app(0)
    conn = app.pool.acquire.return_value
    calls = []
    conn.ensure_connection.side_effect = lambda **kw: calls.append(('ensure', kw))
    type(conn).default_channel = property(
        lambda self: calls.append(('channel', None)) or _channel
    )

    bp.measure_queue_depth(app, KNOBS.settings)

    assert calls == [('ensure', {'max_retries': 0}), ('channel', None)]


def exhausted_app():
    """A Celery app stand-in whose connection pool has nothing free."""
    app = MagicMock()
    app.pool.LimitExceeded = POOL_LIMIT_EXCEEDED
    app.pool.acquire.side_effect = POOL_LIMIT_EXCEEDED(10)
    return app


def test_pool_exhaustion_is_translated_not_leaked():
    """kombu's own exception would log only the pool size."""
    app = exhausted_app()

    with pytest.raises(bp.BrokerPoolExhausted):
        bp.measure_queue_depth(app, KNOBS.settings)

    app.pool.acquire.return_value.release.assert_not_called()


# --- the decision ---------------------------------------------------------


async def test_admits_below_the_limit(limit_10):
    with patch.object(bp, 'measure_queue_depth', return_value=9):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 9)
        await bp.ensure_queue_capacity(APP, KNOBS.settings)  # does not raise


async def test_refuses_at_the_limit(limit_10):
    """The limit is inclusive: exactly MAX_QUEUE_DEPTH refuses."""
    with patch.object(bp, 'measure_queue_depth', return_value=10):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 10)

        with pytest.raises(QueueBackpressure) as exc_info:
            await bp.ensure_queue_capacity(APP, KNOBS.settings)

    assert exc_info.value.depth == 10
    assert exc_info.value.limit == 10
    assert exc_info.value.retry_after == 30


async def test_refuses_above_the_limit(limit_10):
    with patch.object(bp, 'measure_queue_depth', return_value=11):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 11)


async def test_backpressure_is_not_a_value_error(limit_10):
    """The controllers map ValueError to 422."""
    with patch.object(bp, 'measure_queue_depth', return_value=10):
        with pytest.raises(QueueBackpressure) as exc_info:
            await bp.ensure_queue_capacity(APP, KNOBS.settings)

    assert not isinstance(exc_info.value, ValueError)


# --- disabled -------------------------------------------------------------


@pytest.mark.parametrize('limit', [0, -1])
async def test_non_positive_limit_disables_the_gate_without_probing(monkeypatch, limit):
    """A deployment that does not want the gate must not pay for it."""
    KNOBS.set(max_queue_depth=limit)

    with patch.object(bp, 'measure_queue_depth') as probe:
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, None)
        await bp.ensure_queue_capacity(APP, KNOBS.settings)

    probe.assert_not_called()


@pytest.mark.parametrize('limit', [0, -1])
def test_disabled_limit_does_not_divide_by_zero(monkeypatch, limit):
    KNOBS.set(max_queue_depth=limit)

    with patch.object(bp, 'measure_queue_depth', return_value=5):
        assert bp._current_depth(APP, KNOBS.settings) == 5


# --- fail open ------------------------------------------------------------


async def test_probe_failure_fails_open(limit_10, caplog):
    """Could-not-measure is not evidence of saturation."""
    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('broker down')):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, None)
        await bp.ensure_queue_capacity(APP, KNOBS.settings)  # does not raise

    assert 'probe failed' in caplog.text


async def test_pool_exhaustion_is_just_another_failed_probe(limit_10, caplog):
    with patch.object(
        bp,
        'measure_queue_depth',
        side_effect=bp.BrokerPoolExhausted('no broker connection free after 2.0s: 10'),
    ):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, None)

    assert 'no broker connection free' in caplog.text

    with patch.object(bp, 'measure_queue_depth', return_value=12):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)


# --- no new reading: answer from the last one -----------------------------


def blind_after(monkeypatch, depth):
    """Take one good reading of `depth`, then return a clock to move time."""
    KNOBS.set(queue_depth_cache_ttl_seconds=1.0)
    clock = [1000.0]
    monkeypatch.setattr(bp.time, 'monotonic', lambda: clock[0])
    with patch.object(bp, 'measure_queue_depth', return_value=depth):
        assert bp._current_depth(APP, KNOBS.settings) == depth
    return clock


async def test_a_failed_probe_does_not_forget_a_saturated_queue(limit_10, monkeypatch):
    clock = blind_after(monkeypatch, depth=12)
    clock[0] += 5.0

    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down')) as probe:
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)
        with pytest.raises(QueueBackpressure):
            await bp.ensure_queue_capacity(APP, KNOBS.settings)

    assert probe.call_count == 2  # still trying to measure each time


async def test_an_outage_keeps_refusing_a_saturated_queue(limit_10, monkeypatch):
    clock = blind_after(monkeypatch, depth=12)
    clock[0] += 2.0

    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down')) as probe:
        for _ in range(6):
            assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)

    # Keeps probing, so it sees the recovery on the next call.
    assert probe.call_count == 6


async def test_an_outage_keeps_admitting_below_the_limit(limit_10, monkeypatch):
    clock = blind_after(monkeypatch, depth=3)
    clock[0] += 2.0

    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down')):
        for _ in range(6):
            assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 3)


async def test_a_reading_past_the_ceiling_stops_being_believed(
    limit_10, monkeypatch, caplog
):
    """Otherwise a broken probe could refuse work forever."""
    clock = blind_after(monkeypatch, depth=12)

    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down')):
        clock[0] += bp._MAX_STALENESS_SECONDS - 1.0
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)

        clock[0] += 2.0  # now past the ceiling
        assert 'enqueueing ungated' not in caplog.text
        for _ in range(4):
            assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, None)
        await bp.ensure_queue_capacity(APP, KNOBS.settings)  # does not raise

    # Logged once per window, not once per request.
    assert caplog.text.count('enqueueing ungated') == 1
    assert 'last was 12' in caplog.text


async def test_an_outage_is_logged_once_and_so_is_the_recovery(
    limit_10, monkeypatch, caplog
):
    clock = blind_after(monkeypatch, depth=12)
    clock[0] += 2.0

    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down')) as probe:
        for _ in range(8):
            await bp.queue_is_saturated(APP, KNOBS.settings)
        assert probe.call_count == 8
        assert caplog.text.count('probe failed') == 1

        clock[0] += bp._MAX_STALENESS_SECONDS + 1.0  # still down a window later
        await bp.queue_is_saturated(APP, KNOBS.settings)
        assert caplog.text.count('probe failed') == 2

    assert 'working again' not in caplog.text
    with patch.object(bp, 'measure_queue_depth', return_value=4):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 4)
        clock[0] += 2.0
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 4)
    assert caplog.text.count('working again') == 1

    # A second outage is logged at once.
    clock[0] += 2.0
    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down again')):
        await bp.queue_is_saturated(APP, KNOBS.settings)
    assert caplog.text.count('probe failed') == 3


async def test_a_refusal_logs_how_old_its_evidence_is(limit_10, monkeypatch, caplog):
    """A 429 decided on a 20s-old reading must not read like a live one."""
    clock = blind_after(monkeypatch, depth=12)
    assert 'reading 0.0s old' not in caplog.text  # nothing refused yet

    assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)
    assert 'reading 0.0s old' in caplog.text

    clock[0] += 20.0
    with patch.object(bp, 'measure_queue_depth', side_effect=OSError('down')):
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)
    assert 'reading 20.0s old' in caplog.text


# --- the TTL cache --------------------------------------------------------


async def test_depth_is_reused_within_the_ttl(limit_10, monkeypatch):
    KNOBS.set(queue_depth_cache_ttl_seconds=1.0)
    clock = [1000.0]
    monkeypatch.setattr(bp.time, 'monotonic', lambda: clock[0])

    with patch.object(bp, 'measure_queue_depth', return_value=3) as probe:
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 3)
        clock[0] += 0.5
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 3)

    assert probe.call_count == 1


async def test_depth_is_remeasured_after_the_ttl(limit_10, monkeypatch):
    KNOBS.set(queue_depth_cache_ttl_seconds=1.0)
    clock = [1000.0]
    monkeypatch.setattr(bp.time, 'monotonic', lambda: clock[0])

    with patch.object(bp, 'measure_queue_depth', side_effect=[3, 12]) as probe:
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (False, 3)
        clock[0] += 1.5
        assert await bp.queue_is_saturated(APP, KNOBS.settings) == (True, 12)

    assert probe.call_count == 2


class HeldProbe:
    """A probe that blocks until released, so contention is deterministic."""

    def __init__(self, depth):
        self.depth = depth
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        self.started.set()
        assert self.release.wait(timeout=5), 'probe was never released'
        return self.depth

    def run_in_thread(self):
        """Start a prober and return once it is actually inside the probe."""
        result = []
        thread = threading.Thread(
            target=lambda: result.append(bp._current_depth(APP, KNOBS.settings))
        )
        thread.start()
        assert self.started.wait(timeout=5), 'probe never started'
        return thread, result

    def finish(self, thread):
        self.release.set()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_callers_do_not_park_behind_an_in_flight_probe(limit_10, monkeypatch):
    KNOBS.set(queue_depth_cache_ttl_seconds=60.0)
    probe = HeldProbe(4)

    with patch.object(bp, 'measure_queue_depth', side_effect=probe):
        thread, probed = probe.run_in_thread()

        # The probe holds the lock and there is no reading yet: admit at once.
        assert [bp._current_depth(APP, KNOBS.settings) for _ in range(7)] == [None] * 7

        probe.finish(thread)

    assert probe.calls == 1
    assert probed == [4]


def test_in_flight_probe_serves_the_previous_value(limit_10, monkeypatch):
    """Once there is a previous value, contended callers reuse it."""
    KNOBS.set(queue_depth_cache_ttl_seconds=0.0)

    with patch.object(bp, 'measure_queue_depth', return_value=4):
        assert bp._current_depth(APP, KNOBS.settings) == 4

    probe = HeldProbe(9)
    with patch.object(bp, 'measure_queue_depth', side_effect=probe):
        thread, probed = probe.run_in_thread()

        assert [bp._current_depth(APP, KNOBS.settings) for _ in range(3)] == [4, 4, 4]

        probe.finish(thread)

    assert probed == [9]


def test_a_wedged_probe_stops_being_believed(limit_10, monkeypatch):
    KNOBS.set(queue_depth_cache_ttl_seconds=0.0)
    monkeypatch.setattr(bp, '_MAX_STALENESS_SECONDS', 30.0)

    clock = [1000.0]
    monkeypatch.setattr(bp.time, 'monotonic', lambda: clock[0])

    with patch.object(bp, 'measure_queue_depth', return_value=99):
        assert bp._current_depth(APP, KNOBS.settings) == 99

    probe = HeldProbe(1)
    with patch.object(bp, 'measure_queue_depth', side_effect=probe):
        thread, _probed = probe.run_in_thread()

        clock[0] += 29.0
        assert bp._current_depth(APP, KNOBS.settings) == 99

        # Past the ceiling.
        clock[0] += 2.0
        assert bp._current_depth(APP, KNOBS.settings) is None

        probe.finish(thread)


# --- the warn watermark ---------------------------------------------------


async def test_warns_at_the_watermark(limit_10, monkeypatch, caplog):
    KNOBS.set(queue_depth_warn_ratio=0.8)

    with patch.object(bp, 'measure_queue_depth', return_value=8):
        await bp.queue_is_saturated(APP, KNOBS.settings)

    assert 'queue depth 8' in caplog.text


async def test_does_not_warn_below_the_watermark(limit_10, monkeypatch, caplog):
    KNOBS.set(queue_depth_warn_ratio=0.8)

    with patch.object(bp, 'measure_queue_depth', return_value=7):
        await bp.queue_is_saturated(APP, KNOBS.settings)

    assert 'queue depth' not in caplog.text


# --- settings from config.ini ---------------------------------------------


def test_config_strings_are_coerced():
    """config.ini hands every value over as a string."""
    settings = CeleryProducerSettings(
        max_queue_depth='250',
        queue_depth_cache_ttl_seconds='0.5',
        queue_depth_warn_ratio='0.9',
        backpressure_retry_after_seconds='45',
        broker_socket_timeout_seconds='3',
    )

    assert settings.max_queue_depth == 250
    assert settings.queue_depth_cache_ttl_seconds == 0.5
    assert settings.queue_depth_warn_ratio == 0.9
    assert settings.backpressure_retry_after_seconds == 45
    assert settings.broker_socket_timeout_seconds == 3.0


@pytest.mark.parametrize('raw', [None, '', '   ', 'not-a-number'])
def test_unusable_config_values_fall_back_to_the_default(raw):
    """None is what the container passes for a key the ini lacks."""
    settings = CeleryProducerSettings(
        max_queue_depth=raw,
        queue_depth_cache_ttl_seconds=raw,
        queue_depth_warn_ratio=raw,
        backpressure_retry_after_seconds=raw,
        broker_socket_timeout_seconds=raw,
    )

    assert settings == CeleryProducerSettings()
    assert settings.max_queue_depth == 10000


async def test_the_configured_retry_after_reaches_the_exception(limit_10):
    KNOBS.set(backpressure_retry_after_seconds='75')

    with patch.object(bp, 'measure_queue_depth', return_value=10):
        with pytest.raises(QueueBackpressure) as exc_info:
            await bp.ensure_queue_capacity(APP, KNOBS.settings)

    assert exc_info.value.retry_after == 75


def test_the_configured_socket_timeout_bounds_the_pool_wait():
    app, _channel = fake_app(0)
    KNOBS.set(broker_socket_timeout_seconds='0.25')

    bp.measure_queue_depth(app, KNOBS.settings)

    assert app.pool.acquire.call_args.kwargs['timeout'] == 0.25
