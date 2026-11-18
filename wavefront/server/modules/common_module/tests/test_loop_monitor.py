"""Event-loop lag monitor: detection, stack capture, metrics, listeners, logging.

Uses short intervals and real blocking (time.sleep on the loop) so the timing
is genuine; thresholds leave wide margins to stay stable on slow CI.
"""

import asyncio
import threading
import time
from unittest.mock import patch

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from common_module.telemetry import loop_monitor as module
from common_module.telemetry.loop_monitor import (
    BLOCKED_METRIC,
    LAG_METRIC,
    EventLoopMonitor,
    LoopMonitorSettings,
    add_loop_block_listener,
    remove_loop_block_listener,
    start_event_loop_monitor,
)

FAST = LoopMonitorSettings(
    threshold_ms=50, interval_ms=20, stack_threshold_ms=100, log_cooldown_seconds=30
)


class Collector:
    """Listener that records events and lets a test wait for them."""

    def __init__(self):
        self.events = []
        self._cond = threading.Condition()

    def __call__(self, event):
        with self._cond:
            self.events.append(event)
            self._cond.notify_all()

    def wait_for(self, count, timeout=3.0):
        with self._cond:
            return self._cond.wait_for(lambda: len(self.events) >= count, timeout)


@pytest.fixture
def collector():
    listener = Collector()
    add_loop_block_listener(listener)
    yield listener
    remove_loop_block_listener(listener)


@pytest.fixture
def reader():
    return InMemoryMetricReader()


@pytest.fixture
async def monitor(reader):
    m = EventLoopMonitor(
        FAST, 'test-service', meter_provider=MeterProvider(metric_readers=[reader])
    )
    m.start()
    await asyncio.sleep(0.05)  # let the heartbeat settle
    yield m
    await m.stop()


def block_the_loop_for_a_while(seconds):
    time.sleep(seconds)  # deliberately blocking: this is what the monitor must catch


async def test_block_is_reported_with_lag_and_stack(monitor, collector):
    block_the_loop_for_a_while(0.3)
    await asyncio.sleep(0.05)

    assert collector.wait_for(1)
    event = collector.events[0]
    assert event.lag_s >= 0.25
    assert event.service == 'test-service'
    assert event.stack is not None
    assert 'block_the_loop_for_a_while' in event.stack


async def test_short_block_has_no_stack(reader, collector):
    """Over the threshold but under stack_threshold_ms: reported, no stack."""
    # A 150 ms block against a 50 ms threshold and a 1 s stack threshold: wide
    # margins both ways, so scheduler jitter on a busy CI runner can't flip it.
    settings = LoopMonitorSettings(
        threshold_ms=50,
        interval_ms=20,
        stack_threshold_ms=1000,
        log_cooldown_seconds=30,
    )
    m = EventLoopMonitor(
        settings, 'test-service', meter_provider=MeterProvider(metric_readers=[reader])
    )
    m.start()
    try:
        await asyncio.sleep(0.05)  # let the heartbeat settle
        block_the_loop_for_a_while(0.15)
        await asyncio.sleep(0.05)

        assert collector.wait_for(1)
        assert collector.events[0].stack is None
    finally:
        await m.stop()


async def test_idle_loop_reports_nothing(monitor, collector):
    await asyncio.sleep(0.3)

    assert collector.events == []


def _points(reader, name):
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics if data else []:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return list(metric.data.data_points)
    return []


async def test_metrics_record_lag_and_blocks(monitor, collector, reader):
    block_the_loop_for_a_while(0.2)
    await asyncio.sleep(0.1)
    assert collector.wait_for(1)

    (lag,) = _points(reader, LAG_METRIC)
    assert lag.count >= 3  # every heartbeat is recorded, not only blocks
    assert lag.max >= 0.15
    assert 0.25 in lag.explicit_bounds  # seconds-scale buckets, not the ms defaults
    (blocked,) = _points(reader, BLOCKED_METRIC)
    assert blocked.value >= 1


async def test_failing_listener_does_not_stop_monitoring(monitor, collector):
    def broken(_event):
        raise RuntimeError('listener bug')

    add_loop_block_listener(broken)
    try:
        block_the_loop_for_a_while(0.1)
        await asyncio.sleep(0.05)
        block_the_loop_for_a_while(0.1)
        await asyncio.sleep(0.05)

        assert collector.wait_for(2)
    finally:
        remove_loop_block_listener(broken)


async def test_listeners_run_off_the_event_loop(monitor, collector):
    loop_thread = threading.get_ident()
    threads = []

    def record_thread(_event):
        threads.append(threading.get_ident())

    add_loop_block_listener(record_thread)
    try:
        block_the_loop_for_a_while(0.1)
        await asyncio.sleep(0.05)

        assert collector.wait_for(1)
        assert threads and loop_thread not in threads
    finally:
        remove_loop_block_listener(record_thread)


async def test_warnings_are_rate_limited(monitor, collector):
    with patch.object(module.logger, 'warning') as warning:
        block_the_loop_for_a_while(0.1)
        await asyncio.sleep(0.05)
        block_the_loop_for_a_while(0.1)
        await asyncio.sleep(0.05)
        assert collector.wait_for(2)

    messages = [call.args[0] for call in warning.call_args_list]
    assert len(messages) == 1
    assert messages[0].startswith('Event loop blocked for ')


async def test_stop_is_clean(reader):
    m = EventLoopMonitor(
        FAST, 'svc', meter_provider=MeterProvider(metric_readers=[reader])
    )
    m.start()
    task, watchdog = m._task, m._watchdog
    await asyncio.sleep(0.05)

    await m.stop()

    assert task.done()
    assert not watchdog.is_alive()
    await m.stop()  # a second stop is harmless


# --- settings --------------------------------------------------------------------


def test_settings_parse_config_strings():
    settings = LoopMonitorSettings.from_mapping(
        {
            'enabled': 'true',
            'threshold_ms': '50',
            'interval_ms': '100',
            'stack_threshold_ms': '250',
            'log_cooldown_seconds': '30',
        }
    )

    assert settings == LoopMonitorSettings(
        enabled=True,
        threshold_ms=50,
        interval_ms=100,
        stack_threshold_ms=250,
        log_cooldown_seconds=30,
    )


def test_missing_section_uses_defaults():
    assert LoopMonitorSettings.from_mapping(None) == LoopMonitorSettings()


def test_non_positive_values_are_rejected():
    with pytest.raises(ValueError, match='interval_ms'):
        LoopMonitorSettings.from_mapping({'interval_ms': '0'})


async def test_disabled_monitor_does_not_start():
    assert start_event_loop_monitor({'enabled': 'false'}, service='svc') is None


async def test_start_helper_starts_and_stops():
    monitor = start_event_loop_monitor({'interval_ms': '20'}, service='svc')
    try:
        assert monitor is not None
        assert monitor._task is not None
    finally:
        await monitor.stop()
