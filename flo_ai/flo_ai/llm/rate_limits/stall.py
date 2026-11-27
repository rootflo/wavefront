"""One call's waits and retries, bounded by its stall budget."""

from typing import Any, Optional, Tuple

from flo_ai.llm.rate_limits.errors import LLMProviderError, LLMRateLimited
from flo_ai.llm.rate_limits.gate import get_gate
from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.options import resolve_max_wait, resolve_retries
from flo_ai.telemetry.instrumentation import llm_metrics
from flo_ai.utils.logger import logger

MAX_BACKOFF = 30.0
WAKE_JITTER = 1.0
TRANSIENT_RETRIES = 3
TRANSIENT_BASE_DELAY = 0.5


class Stall:
    """One call's progress through the gate and its stall budget."""

    def __init__(self, llm: Any, provider: str):
        self.provider = provider
        self.model = getattr(llm, 'model', '') or ''
        self.gate = get_gate(llm.rate_limit_scope())
        self.budget = resolve_max_wait(llm)
        self.retries = resolve_retries(llm)
        self.started = self.gate.clock()
        self.attempt = 0
        self.transient_retries = 0
        # The attempt whose wait was last logged, so a split wait logs once.
        self.announced: Optional[int] = None
        self.last: Optional[Tuple[Exception, Classification]] = None

    def _left(self) -> float:
        return self.started + self.budget - self.gate.clock()

    def _exhausted(self) -> LLMRateLimited:
        waited = self.gate.clock() - self.started
        error, info = self.last if self.last else (None, None)
        if error is None:
            message = (
                f'{self.provider} is cooling down after a rate limit for longer '
                f'than the {self.budget:.0f}s budget'
            )
        else:
            attempts = f'{self.attempt} attempt' + ('s' if self.attempt != 1 else '')
            message = (
                f'{self.provider} rate limit persisted for {waited:.0f}s over '
                f'{attempts} (budget {self.budget:.0f}s, '
                f'{self.retries} retries): {error}'
            )
        return LLMRateLimited(
            message,
            provider=self.provider,
            status=info.status if info else 429,
            retry_after=info.retry_after if info else self.gate.remaining(),
            waited_s=waited,
            original_error=error,
        )

    async def wait_turn(self) -> None:
        while (remaining := self.gate.remaining()) > 0:
            # End times, not durations: two clock reads drift apart.
            if self.gate.cooldown_until > self.started + self.budget:
                error = self.last[0] if self.last else None
                raise self._exhausted() from error
            wait = min(remaining + self.gate.rand(0, WAKE_JITTER), self._left())
            self._announce(wait)
            await self.gate.sleep(wait)
            llm_metrics.record_rate_limit_wait(wait * 1000, self.model, self.provider)

    def _announce(self, wait: float) -> None:
        if self.announced == self.attempt:
            return
        self.announced = self.attempt
        if self.attempt == 0:
            # No 429 of this call's own yet: another call set the cooldown.
            logger.warning(
                f'{self.provider} cooling down on {self.model} after a rate '
                f'limit; waiting {wait:.0f}s before calling'
            )
            return
        status = self.last[1].status if self.last else 429
        # Warn once per call; later retries are routine.
        log = logger.warning if self.attempt == 1 else logger.info
        log(
            f'{self.provider} rate-limited ({status}) on {self.model}; retrying '
            f'in {wait:.1f}s (attempt {self.attempt + 1} of '
            f'{self.retries + 1}, {max(0.0, self._left()):.0f}s of '
            f'{self.budget:.0f}s budget left)'
        )

    async def absorb(
        self, error: Exception, info: Classification, retry: bool = True
    ) -> None:
        """Get ready to retry ``error``, or raise it typed.

        A rate limit goes onto the shared gate and wait_turn() does the waiting.
        A transient failure is this call's alone, so it backs off here without
        pausing anyone else.
        """
        if info.kind != 'rate_limit':
            if retry and await self._back_off_transient(error, info):
                return
            raise LLMProviderError(
                f'{self.provider} request failed: {error}',
                provider=self.provider,
                status=info.status,
                transient=info.kind == 'transient',
                original_error=error,
            ) from error

        if info.retry_after:
            delay = info.retry_after
        else:
            # Equal jitter: full jitter can extend the shared gate by ~0s.
            ceiling = min(MAX_BACKOFF, 2.0**self.attempt)
            delay = ceiling / 2 + self.gate.rand(0, ceiling / 2)
        self.gate.extend(delay)
        llm_metrics.record_rate_limited(self.model, self.provider)
        self.attempt += 1
        self.last = (error, info)
        if self.attempt > self.retries:
            raise self._exhausted() from error

    async def _back_off_transient(self, error: Exception, info: Classification) -> bool:
        if info.kind != 'transient' or self.transient_retries >= TRANSIENT_RETRIES:
            return False
        delay = (
            TRANSIENT_BASE_DELAY
            * 2**self.transient_retries
            * (1 - self.gate.rand(0, 0.25))
        )
        if delay > self._left():
            return False
        self.transient_retries += 1
        logger.info(
            f'{self.provider} request failed on {self.model}; retrying in '
            f'{delay:.1f}s: {error}'
        )
        await self.gate.sleep(delay)
        return True
