"""Unit tests for SlidingWindowRateLimiter, driven by a fake clock."""

import threading

import pytest

from inference_app.middleware.rate_limiter import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


def admitted(limiter: SlidingWindowRateLimiter, count: int) -> int:
    return sum(limiter.acquire() is None for _ in range(count))


def test_admits_up_to_the_per_second_limit():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter([(4, 1.0)], clock=clock)

    assert admitted(limiter, 4) == 4
    assert limiter.acquire() == pytest.approx(1.0)


def test_window_slides_rather_than_resetting():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter([(4, 1.0)], clock=clock)

    assert admitted(limiter, 2) == 2
    clock.advance(0.5)
    assert admitted(limiter, 2) == 2

    clock.advance(0.6)  # the first two have left the window, the last two not
    assert admitted(limiter, 3) == 2
    assert limiter.acquire() == pytest.approx(0.4)


def test_rejected_requests_do_not_count_against_the_limit():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter([(1, 1.0)], clock=clock)

    assert limiter.acquire() is None
    for _ in range(10):
        assert limiter.acquire() is not None

    clock.advance(1.0)
    assert limiter.acquire() is None


def test_per_minute_limit_applies_even_when_per_second_has_room():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter([(4, 1.0), (6, 60.0)], clock=clock)

    assert admitted(limiter, 4) == 4
    clock.advance(1.0)
    assert admitted(limiter, 4) == 2

    retry_after = limiter.acquire()
    assert retry_after == pytest.approx(59.0)


def test_retry_after_is_the_longest_wait_across_windows():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter([(2, 1.0), (2, 60.0)], clock=clock)

    assert admitted(limiter, 2) == 2

    assert limiter.acquire() == pytest.approx(60.0)


def test_zero_disables_a_window():
    limiter = SlidingWindowRateLimiter([(0, 1.0), (3, 60.0)], clock=FakeClock())

    assert admitted(limiter, 5) == 3


def test_no_limits_admits_everything():
    limiter = SlidingWindowRateLimiter([], clock=FakeClock())

    assert admitted(limiter, 1000) == 1000


def test_concurrent_callers_never_exceed_the_limit():
    limiter = SlidingWindowRateLimiter([(4, 60.0)])
    results = []
    results_lock = threading.Lock()

    def worker():
        outcome = limiter.acquire() is None
        with results_lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results) == 4
