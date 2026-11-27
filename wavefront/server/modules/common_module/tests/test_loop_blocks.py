"""Event-loop blocks reported to Sentry (common_module.error_reporting.loop_blocks)."""

from __future__ import annotations

import asyncio
import logging
import time

import pytest

from common_module.error_reporting import (
    ErrorReportingSettings,
    start_loop_block_reporting,
    stop_loop_block_reporting,
)
from common_module.error_reporting.loop_blocks import (
    GROUP_COOLDOWN_SECONDS,
    MAX_EVENTS_PER_HOUR,
    LoopBlockReporter,
    blocking_location,
)
from common_module.telemetry import loop_monitor
from common_module.telemetry.loop_monitor import (
    EventLoopMonitor,
    LoopBlockEvent,
    LoopMonitorSettings,
)

SITE = '/app/.venv/lib/python3.11/site-packages'
WS = '/app/wavefront/server/modules'


def _frame(path: str, function: str, line: int = 10) -> str:
    return f'  File "{path}", line {line}, in {function}\n    code()\n'


STACK = (
    _frame('/usr/lib/python3.11/asyncio/base_events.py', 'run_forever')
    + _frame(
        f'{WS}/user_management_module/user_management_module/authorization/require_auth.py',
        'dispatch',
    )
    + _frame(
        f'{WS}/db_repo_module/db_repo_module/cache/cache_manager.py', 'get_str', 120
    )
    + _frame(f'{SITE}/redis/client.py', 'execute_command')
    + _frame(f'{SITE}/redis/connection.py', 'read_response')
)


def _event(stack: str | None = STACK, lag_s: float = 0.8) -> LoopBlockEvent:
    return LoopBlockEvent(lag_s=lag_s, started_at=0.0, stack=stack, service='floware')


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def no_listener_left_behind():
    yield
    stop_loop_block_reporting()


# -- where the block is ---------------------------------------------------------


def test_location_is_the_innermost_workspace_frame():
    assert blocking_location(STACK) == 'db_repo_module.cache.cache_manager.get_str'


def test_location_ignores_line_numbers():
    moved = STACK.replace('line 120', 'line 999')
    assert blocking_location(moved) == blocking_location(STACK)


def test_location_skips_the_monitor_itself():
    stack = STACK + _frame(
        f'{WS}/common_module/common_module/telemetry/loop_monitor.py', '_heartbeat'
    )
    assert blocking_location(stack) == 'db_repo_module.cache.cache_manager.get_str'


def test_deep_sdk_stall_is_grouped_on_the_outermost_library():
    # The monitor keeps only the innermost frames, so a stall deep inside an
    # SDK can show no workspace frame at all.
    stack = (
        _frame(f'{SITE}/botocore/client.py', '_make_api_call')
        + _frame(f'{SITE}/botocore/endpoint.py', '_send')
        + _frame(f'{SITE}/urllib3/connectionpool.py', 'urlopen')
        + _frame('/usr/lib/python3.11/ssl.py', 'recv_into')
    )
    assert blocking_location(stack) == 'library:botocore'


def test_a_file_named_like_a_workspace_package_is_not_one():
    stack = _frame(f'{SITE}/flo_ai/utils/flo_utils.py', 'helper')
    assert blocking_location(stack) == 'library:flo_ai'


def test_stdlib_only_stack_has_no_location():
    stack = _frame('/usr/lib/python3.11/ssl.py', 'recv_into')
    assert blocking_location(stack) is None


def test_odd_paths_do_not_raise():
    assert blocking_location('  File "/", line 1, in x\n') is None


# -- what is sent ---------------------------------------------------------------


def test_block_with_a_stack_becomes_a_warning_event(start_sentry):
    transport = start_sentry()
    LoopBlockReporter()(_event())

    (event,) = transport.events
    assert event['level'] == 'warning'
    assert event['fingerprint'] == [
        'event-loop-blocked',
        'db_repo_module.cache.cache_manager.get_str',
    ]
    assert event['message'] == (
        'Event loop blocked for 800 ms in db_repo_module.cache.cache_manager.get_str'
    )
    assert event['tags']['event_loop.blocked'] == 'true'
    assert event['extra']['lag_ms'] == 800
    assert 'cache_manager.py' in event['extra']['stack']


def test_loop_block_event_has_no_stale_breadcrumbs(start_sentry):
    transport = start_sentry()
    logging.getLogger('floware').warning('unrelated warning before the block')
    LoopBlockReporter()(_event())

    (event,) = transport.events
    assert not (event.get('breadcrumbs') or {}).get('values')


def test_block_without_a_stack_is_not_sent(start_sentry):
    transport = start_sentry()
    LoopBlockReporter()(_event(stack=None))
    assert transport.events == []


def test_unattributed_blocks_share_one_group(start_sentry):
    transport = start_sentry()
    LoopBlockReporter()(_event(stack=_frame('/usr/lib/python3.11/ssl.py', 'read')))

    (event,) = transport.events
    assert event['fingerprint'] == ['event-loop-blocked', 'unattributed']


# -- how often ------------------------------------------------------------------


def test_one_event_per_group_per_cooldown(start_sentry):
    transport = start_sentry()
    clock = _Clock()
    reporter = LoopBlockReporter(clock=clock)

    reporter(_event())
    clock.now += GROUP_COOLDOWN_SECONDS - 1
    reporter(_event())
    assert len(transport.events) == 1

    clock.now += 1
    reporter(_event())
    assert len(transport.events) == 2


def test_hourly_cap_across_groups(start_sentry):
    # Lift the process-wide per-minute cap so only the hourly cap is tested.
    transport = start_sentry(max_events_per_minute=1000)
    clock = _Clock()
    reporter = LoopBlockReporter(clock=clock)

    def block_in(function: str) -> LoopBlockEvent:
        return _event(stack=_frame(f'{WS}/floware/floware/x.py', function))

    for index in range(MAX_EVENTS_PER_HOUR + 5):
        reporter(block_in(f'f{index}'))
    assert len(transport.events) == MAX_EVENTS_PER_HOUR

    clock.now += 3600
    reporter(block_in('after_the_hour'))
    assert len(transport.events) == MAX_EVENTS_PER_HOUR + 1


# -- switching it on and off ----------------------------------------------------


def _listeners() -> list:
    with loop_monitor._listeners_lock:
        return list(loop_monitor._listeners)


def test_not_registered_when_error_reporting_is_off():
    assert start_loop_block_reporting() is False
    assert not any(isinstance(item, LoopBlockReporter) for item in _listeners())


def test_not_registered_when_switched_off(start_sentry):
    start_sentry(report_loop_blocks=False)
    assert start_loop_block_reporting() is False
    assert not any(isinstance(item, LoopBlockReporter) for item in _listeners())


def test_registered_once_and_removed(start_sentry):
    start_sentry()
    assert start_loop_block_reporting() is True
    assert start_loop_block_reporting() is True
    assert sum(isinstance(item, LoopBlockReporter) for item in _listeners()) == 1

    stop_loop_block_reporting()
    assert not any(isinstance(item, LoopBlockReporter) for item in _listeners())
    stop_loop_block_reporting()  # safe twice


@pytest.mark.parametrize(
    'raw, expected',
    [('', True), ('true', True), ('FALSE', False), ('off', False), ('maybe', True)],
)
def test_loop_blocks_setting(raw, expected, caplog):
    with caplog.at_level(logging.WARNING):
        settings = ErrorReportingSettings.from_config(
            {'sentry': {'loop_blocks': raw}}, default_service_name='s'
        )
    assert settings.report_loop_blocks is expected
    if raw == 'maybe':
        assert 'loop_blocks' in caplog.text


# -- end to end with the real monitor -------------------------------------------


def _block_the_loop(seconds: float) -> None:
    time.sleep(seconds)  # deliberately blocking, on the event loop


async def test_real_monitor_block_reaches_sentry(start_sentry):
    transport = start_sentry()
    assert start_loop_block_reporting() is True
    monitor = EventLoopMonitor(
        LoopMonitorSettings(
            threshold_ms=50,
            interval_ms=20,
            stack_threshold_ms=100,
            log_cooldown_seconds=30,
        ),
        service='test',
    )
    monitor.start()
    try:
        await asyncio.sleep(0.1)
        _block_the_loop(0.4)
        # Let the heartbeat wake up and the watchdog thread call the listener.
        for _ in range(50):
            await asyncio.sleep(0.05)
            if transport.events:
                break
    finally:
        await monitor.stop()

    (event,) = transport.events
    assert event['fingerprint'][1].endswith('test_loop_blocks._block_the_loop')
    assert event['extra']['lag_ms'] >= 300


def test_reporter_is_harmless_without_a_sentry_client():
    # Without a client the SDK drops the message; the call must not raise.
    LoopBlockReporter()(_event())
