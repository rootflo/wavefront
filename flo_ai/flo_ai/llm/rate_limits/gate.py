"""The cooldown every call on one provider scope shares.

Per process: each worker and pod has its own gates.
"""

import asyncio
import random
import time
from typing import Any, Callable, Dict

from flo_ai.llm.rate_limits.models import RateLimitScope


class RateLimitGate:
    """A cooldown shared by every call on one provider scope."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Any] = asyncio.sleep,
        rand: Callable[[float, float], float] = random.uniform,
    ):
        self.clock = clock
        self.sleep = sleep
        self.rand = rand
        self._cooldown_until = 0.0
        self.last_used = clock()

    @property
    def cooldown_until(self) -> float:
        return self._cooldown_until

    def remaining(self) -> float:
        return max(0.0, self._cooldown_until - self.clock())

    def extend(self, delay: float) -> None:
        self.last_used = self.clock()
        self._cooldown_until = max(self._cooldown_until, self.clock() + delay)

    def idle_for(self) -> float:
        return self.clock() - self.last_used


# One gate per provider, model, endpoint and key: a long-lived process that
# sees many keys would keep every gate forever. Only gates idle this long,
# with no cooldown left, are dropped, so no call is holding one in practice.
GATE_PRUNE_THRESHOLD = 256
GATE_IDLE_SECONDS = 3600.0

_gates: Dict[RateLimitScope, RateLimitGate] = {}


def _prune_idle_gates() -> None:
    for scope, gate in list(_gates.items()):
        if gate.remaining() == 0 and gate.idle_for() > GATE_IDLE_SECONDS:
            _gates.pop(scope, None)


def get_gate(scope: RateLimitScope) -> RateLimitGate:
    gate = _gates.get(scope)
    if gate is None:
        if len(_gates) >= GATE_PRUNE_THRESHOLD:
            _prune_idle_gates()
        gate = _gates[scope] = RateLimitGate()
    else:
        gate.last_used = gate.clock()
    return gate
