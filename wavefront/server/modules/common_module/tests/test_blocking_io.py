"""Named blocking-I/O pools: running off the loop, limits, refusal when full."""

import asyncio
import contextvars
import threading

import pytest

from common_module import blocking_io as module
from common_module.blocking_io import (
    BlockingIoLimits,
    BlockingPoolBusyError,
    configure_blocking_io,
    run_in_pool,
    shutdown_blocking_io,
)


@pytest.fixture(autouse=True)
def fresh_pools():
    """Each test starts with default limits and no pools."""
    shutdown_blocking_io()
    module._limits = BlockingIoLimits()
    yield
    shutdown_blocking_io()
    module._limits = BlockingIoLimits()


async def test_runs_off_the_event_loop_and_returns_the_result():
    loop_thread = threading.get_ident()

    result = await run_in_pool(
        'kms', lambda: (threading.get_ident(), threading.current_thread().name)
    )

    thread_id, name = result
    assert thread_id != loop_thread
    assert name.startswith('blocking-kms')


async def test_arguments_and_exceptions_pass_through():
    assert await run_in_pool('cpu', pow, 2, 10) == 1024

    def boom():
        raise KeyError('nope')

    with pytest.raises(KeyError, match='nope'):
        await run_in_pool('storage', boom)


request_id = contextvars.ContextVar('request_id', default=None)


async def test_context_variables_carry_over():
    request_id.set('req-42')

    assert await run_in_pool('storage', request_id.get) == 'req-42'


async def test_full_pool_refuses_after_the_queue_wait():
    configure_blocking_io({'kms_max_threads': '1', 'queue_wait_seconds': '0.1'})
    release = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        release.wait(5)

    holding = asyncio.ensure_future(run_in_pool('kms', hold))
    await asyncio.to_thread(started.wait, 5)  # the only thread is now busy
    ran = []

    try:
        with pytest.raises(BlockingPoolBusyError) as excinfo:
            await run_in_pool('kms', ran.append, 'should not run')
    finally:
        release.set()
        _ = await holding  # surface any error from the held call

    assert excinfo.value.pool == 'kms'
    await asyncio.sleep(0.05)
    assert ran == []  # refused calls never run


async def test_pools_are_independent():
    """A full kms pool doesn't hold up storage calls."""
    configure_blocking_io({'kms_max_threads': '1', 'queue_wait_seconds': '0.1'})
    release = threading.Event()
    started = threading.Event()

    def hold():
        started.set()
        release.wait(5)

    holding = asyncio.ensure_future(run_in_pool('kms', hold))
    await asyncio.to_thread(started.wait, 5)  # the kms pool is saturated

    try:
        assert await run_in_pool('storage', lambda: 'ok') == 'ok'
    finally:
        release.set()
        _ = await holding  # surface any error from the held call


async def test_unknown_pool_is_rejected():
    with pytest.raises(ValueError, match='Unknown blocking-I/O pool'):
        await run_in_pool('redis', lambda: None)


def test_configure_parses_config_strings():
    limits = configure_blocking_io(
        {
            'kms_max_threads': '3',
            'storage_max_threads': '5',
            'cpu_max_threads': '2',
            'queue_wait_seconds': '2.5',
        }
    )

    assert limits == BlockingIoLimits(
        kms_max_threads=3,
        storage_max_threads=5,
        cpu_max_threads=2,
        queue_wait_seconds=2.5,
    )


def test_missing_section_keeps_defaults():
    assert configure_blocking_io(None) == BlockingIoLimits()


def test_non_positive_values_are_rejected():
    with pytest.raises(ValueError, match='cpu_max_threads'):
        configure_blocking_io({'cpu_max_threads': '0'})


async def test_configure_after_first_use_is_ignored():
    await run_in_pool('cpu', lambda: None)

    limits = configure_blocking_io({'cpu_max_threads': '9'})

    assert limits.cpu_max_threads == BlockingIoLimits().cpu_max_threads


def test_retry_after_rounds_up():
    configure_blocking_io({'queue_wait_seconds': '2.5'})

    assert module.retry_after_seconds() == 3


@pytest.mark.parametrize('bad', ['inf', 'nan', '0'])
def test_queue_wait_must_be_finite_and_positive(bad):
    with pytest.raises(ValueError):
        configure_blocking_io({'queue_wait_seconds': bad})
