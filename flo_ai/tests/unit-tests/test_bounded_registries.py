"""Module-level registries stay bounded in a long-running process.

The rate-limit gate registry kept a gate for every provider, model, endpoint
and key ever seen; the profiler kept every duration it recorded.
"""

from collections import defaultdict

import pytest

from flo_ai.llm.rate_limits import gate as gates
from flo_ai.llm.rate_limits.gate import (
    GATE_IDLE_SECONDS,
    GATE_PRUNE_THRESHOLD,
    RateLimitGate,
    get_gate,
)
from flo_ai.llm.rate_limits.models import RateLimitScope
from flo_ai.utils import profiler


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(gates, '_gates', {})
    return gates._gates


def _scope(i):
    return RateLimitScope(provider='p', model=f'm{i}')


def _fill_with_idle_gates(registry, clock):
    for i in range(GATE_PRUNE_THRESHOLD):
        registry[_scope(i)] = RateLimitGate(clock=clock)
    clock.now += GATE_IDLE_SECONDS + 1


class TestGatePruning:
    def test_idle_gates_are_dropped_once_over_the_threshold(self, registry):
        clock = Clock()
        _fill_with_idle_gates(registry, clock)

        get_gate(_scope('new'))

        assert list(registry) == [_scope('new')]

    def test_a_gate_in_cooldown_is_kept(self, registry):
        clock = Clock()
        _fill_with_idle_gates(registry, clock)
        cooling = registry[_scope(0)]
        cooling._cooldown_until = clock.now + 30

        get_gate(_scope('new'))

        assert registry[_scope(0)] is cooling

    def test_a_recently_used_gate_is_kept(self, registry):
        clock = Clock()
        _fill_with_idle_gates(registry, clock)
        get_gate(_scope(0))  # a call fetching its gate marks it used

        get_gate(_scope('new'))

        assert _scope(0) in registry

    def test_below_the_threshold_nothing_is_dropped(self, registry):
        clock = Clock()
        registry[_scope(0)] = RateLimitGate(clock=clock)
        clock.now += GATE_IDLE_SECONDS + 1

        get_gate(_scope('new'))

        assert _scope(0) in registry


def test_profiler_keeps_totals_not_every_sample(tmp_path, monkeypatch):
    # Patched, not enabled, so a session profiling the suite is left untouched.
    log = open(tmp_path / 'profile.log', 'w', encoding='utf-8')
    monkeypatch.setattr(profiler, '_enabled', True)
    monkeypatch.setattr(profiler, '_file_handle', log)
    monkeypatch.setattr(profiler, '_totals', defaultdict(profiler._SectionStats))

    for duration in (0.1, 0.3, 0.2):
        profiler.record('section', duration)

    stats = profiler._totals['section']
    assert (stats.count, round(stats.total, 6), stats.max) == (3, 0.6, 0.3)
    assert not hasattr(stats, '__dict__')  # fixed size, no sample list

    profiler.write_summary()
    log.close()
    summary = (tmp_path / 'profile.log').read_text()
    assert '600.00       3      200.00      300.00  section' in summary
