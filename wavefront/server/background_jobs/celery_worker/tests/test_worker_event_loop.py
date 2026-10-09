"""Shared worker event-loop lifecycle."""

import asyncio
from unittest.mock import patch

import celery_worker.event_loop as event_loop


def _reset_loop():
    event_loop.close_event_loop()
    event_loop._loop = None


def test_get_event_loop_returns_same_open_loop():
    _reset_loop()
    try:
        loop1 = event_loop.get_event_loop()
        loop2 = event_loop.get_event_loop()
        assert loop1 is loop2
        assert not loop1.is_closed()
    finally:
        _reset_loop()


def test_close_event_loop_is_idempotent():
    _reset_loop()
    try:
        event_loop.get_event_loop()
        event_loop.close_event_loop()
        assert event_loop._loop is None
        event_loop.close_event_loop()  # second call must not raise
    finally:
        _reset_loop()


def test_get_event_loop_creates_new_loop_after_close():
    _reset_loop()
    try:
        first = event_loop.get_event_loop()
        first_id = id(first)
        event_loop.close_event_loop()
        second = event_loop.get_event_loop()
        assert id(second) != first_id
        assert not second.is_closed()
    finally:
        _reset_loop()


def test_drain_tasks_returns_empty_when_nothing_pending():
    loop = asyncio.new_event_loop()
    try:
        assert event_loop._drain_tasks(loop, timeout=0.1) == []
    finally:
        loop.close()


def test_close_event_loop_skips_when_loop_is_running():
    _reset_loop()
    try:
        loop = event_loop.get_event_loop()
        with patch.object(loop, 'is_running', return_value=True):
            event_loop.close_event_loop()
            assert event_loop._loop is loop
            assert not loop.is_closed()
    finally:
        if event_loop._loop is not None:
            event_loop._loop.close()
            event_loop._loop = None
