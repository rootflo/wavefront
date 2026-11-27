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

    @property
    def cooldown_until(self) -> float:
        return self._cooldown_until

    def remaining(self) -> float:
        return max(0.0, self._cooldown_until - self.clock())

    def extend(self, delay: float) -> None:
        self._cooldown_until = max(self._cooldown_until, self.clock() + delay)


_gates: Dict[RateLimitScope, RateLimitGate] = {}


def get_gate(scope: RateLimitScope) -> RateLimitGate:
    gate = _gates.get(scope)
    if gate is None:
        gate = _gates[scope] = RateLimitGate()
    return gate
