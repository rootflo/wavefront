"""bcrypt helpers: the async versions run on the 'cpu' pool, off the event loop."""

import asyncio
import threading
import time
from unittest.mock import patch

import pytest

from common_module.blocking_io import shutdown_blocking_io
from user_management_module.utils import password_utils
from user_management_module.utils.password_utils import (
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)


@pytest.fixture(autouse=True)
def fresh_pools():
    yield
    shutdown_blocking_io()


async def test_async_hash_round_trips_with_sync_verify():
    hashed = await hash_password_async('s3cret!')

    assert verify_password('s3cret!', hashed)
    assert not verify_password('wrong', hashed)


async def test_async_verify_matches_sync_hash():
    hashed = hash_password('s3cret!')

    assert await verify_password_async('s3cret!', hashed) is True
    assert await verify_password_async('wrong', hashed) is False


async def test_bcrypt_runs_off_the_event_loop():
    loop_thread = threading.get_ident()
    threads = []
    real_checkpw = password_utils.bcrypt.checkpw

    def recording_checkpw(*args):
        threads.append(threading.get_ident())
        return real_checkpw(*args)

    hashed = hash_password('pw')
    with patch.object(password_utils.bcrypt, 'checkpw', recording_checkpw):
        await verify_password_async('pw', hashed)

    assert threads and loop_thread not in threads


async def test_loop_stays_responsive_during_a_burst_of_logins():
    """The point of 2d: bcrypt must not hold the loop while it works."""
    hashed = hash_password('pw')
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.ensure_future(ticker())
    started = time.monotonic()
    try:
        await asyncio.gather(*(verify_password_async('pw', hashed) for _ in range(4)))
    finally:
        task.cancel()
    elapsed = time.monotonic() - started

    # With bcrypt on the loop, the ticker would get no turns at all until it finished.
    assert ticks >= max(1, int(elapsed / 0.01) // 3)
