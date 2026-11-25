"""Provider error typing and rate-limit stalling at the LLM boundary.

``@rate_limited`` / ``@rate_limited_stream`` wrap a provider's ``generate`` /
``stream``. Errors are typed here, where only the LLM call is in scope, so a
tool's own httpx failure is never mistaken for a provider failure upstream:

- a 429 (or Anthropic 529) stalls the call, honouring Retry-After, and retries
  until ``rate_limit_max_wait`` seconds have passed or ``rate_limit_retries``
  retries are spent; then ``LLMRateLimited`` is raised
- a 5xx / 408 / timeout / connection error is retried up to
  ``TRANSIENT_RETRIES`` times with a short backoff, inside the same budget
- what is left becomes ``LLMProviderError``, with ``transient`` set for the
  kinds above
- anything unrecognised propagates untouched

This is the only place a provider call is retried. The SDK clients are built
with ``max_retries=0``: their own retries happen inside one call, so they hid
each 429 from the gate and ran past the budget. Callers above (agents, the
router) let ``LLMProviderError`` propagate rather than retrying again.

``rate_limit_max_wait`` and ``rate_limit_retries`` are LLM attributes. Unset
(None), each falls back to its ``FLO_AI_RATE_LIMIT_*`` env var, read when a call
starts, then to the default here. An LLM inference config can set them through
its ``parameters``; see ``apply_rate_limit_options``.

Every caller sharing a provider, endpoint, model and key shares one
``RateLimitGate``, so a 429 seen by one call pauses all of them. The gate is
per process: each worker and pod has its own.

Known costs:

- Calls already in flight when a 429 arrives don't consult the gate.
- The budget is checked between attempts, so a call can overrun it by one
  request's duration.
- The budget is per LLM call. An agent run makes several calls, so its worst
  case stall is a multiple of it.
- ``rate_limit_max_wait=0`` disables retries: a 429 or transient failure is
  raised at once, and a call fails immediately while another caller has the
  gate cooling down.
"""

import asyncio
import math
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import wraps
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import aiohttp
import anthropic
import botocore.exceptions
import httpx
import openai
from google.genai import errors as genai_errors

from flo_ai.models.agent_error import AgentError
from flo_ai.telemetry.instrumentation import llm_metrics
from flo_ai.utils.logger import logger

DEFAULT_RATE_LIMIT_MAX_WAIT = 60.0
# A short Retry-After would otherwise allow dozens of requests per budget.
DEFAULT_RATE_LIMIT_RETRIES = 4
MAX_WAIT_ENV = 'FLO_AI_RATE_LIMIT_MAX_WAIT'
RETRIES_ENV = 'FLO_AI_RATE_LIMIT_RETRIES'
# Keys an LLM inference config's parameters may carry for this layer, and
# whether each must be whole. Never request params: providers reject them.
_OPTION_IS_WHOLE = {'rate_limit_max_wait': False, 'rate_limit_retries': True}
RATE_LIMIT_OPTIONS = frozenset(_OPTION_IS_WHOLE)
MAX_BACKOFF = 30.0
WAKE_JITTER = 1.0
TRANSIENT_RETRIES = 3
TRANSIENT_BASE_DELAY = 0.5

_BOTO_THROTTLE_CODES = frozenset(
    {'ThrottlingException', 'TooManyRequestsException', 'Throttling'}
)


class LLMProviderError(AgentError):
    """A provider call failed in a way the model itself cannot fix."""

    def __init__(
        self,
        message: str,
        *,
        provider: str = '',
        status: Optional[int] = None,
        transient: bool = False,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message, original_error=original_error)
        self.provider = provider
        self.status = status
        self.transient = transient


class LLMRateLimited(LLMProviderError):
    """The provider kept rate-limiting past the call's stall budget."""

    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: str = '',
        status: Optional[int] = 429,
        retry_after: Optional[float] = None,
        waited_s: float = 0.0,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(
            message,
            provider=provider,
            status=status,
            transient=False,
            original_error=original_error,
        )
        self.retry_after = retry_after
        self.waited_s = waited_s


@dataclass(frozen=True)
class Classification:
    kind: str  # 'rate_limit' | 'transient' | 'fatal'
    status: Optional[int] = None
    retry_after: Optional[float] = None


def classify(exc: BaseException) -> Optional[Classification]:
    """Type a provider failure, or None when it isn't one.

    Looks at ``__cause__`` too: the Anthropic and Gemini wrappers re-raise as a
    plain Exception ``from`` the SDK error.
    """
    for candidate in (exc, exc.__cause__):
        if candidate is not None:
            result = _classify_one(candidate)
            if result is not None:
                return result
    return None


def _classify_one(exc: BaseException) -> Optional[Classification]:
    if isinstance(exc, (openai.APIStatusError, anthropic.APIStatusError)):
        status = exc.status_code
        if status == 429:
            # Billing exhausted; waiting can't help.
            if getattr(exc, 'code', None) == 'insufficient_quota':
                return Classification('fatal', status)
            return Classification(
                'rate_limit', status, _header_delay(exc.response.headers)
            )
        if status == 529:
            return Classification(
                'rate_limit', status, _header_delay(exc.response.headers)
            )
        return _by_status(status)

    if isinstance(exc, (openai.APIConnectionError, anthropic.APIConnectionError)):
        return Classification('transient')

    if isinstance(exc, genai_errors.APIError):
        status = exc.code
        if status == 429 or exc.status == 'RESOURCE_EXHAUSTED':
            if _gemini_daily_quota(exc.details):
                return Classification('fatal', status)
            delay = _gemini_retry_delay(exc.details)
            if delay is None and isinstance(exc.response, httpx.Response):
                delay = _header_delay(exc.response.headers)
            return Classification('rate_limit', status, delay)
        return _by_status(status)

    if isinstance(exc, botocore.exceptions.ClientError):
        code = exc.response.get('Error', {}).get('Code', '')
        status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode')
        if code in _BOTO_THROTTLE_CODES or status == 429:
            return Classification('rate_limit', status or 429)
        return _by_status(status)

    if isinstance(exc, botocore.exceptions.BotoCoreError):
        if isinstance(
            exc,
            (
                botocore.exceptions.ConnectionError,
                botocore.exceptions.HTTPClientError,
            ),
        ):
            return Classification('transient')
        return Classification('fatal')

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return Classification(
                'rate_limit', status, _header_delay(exc.response.headers)
            )
        return _by_status(status)

    if isinstance(exc, aiohttp.ClientResponseError):
        if exc.status == 429:
            return Classification(
                'rate_limit', exc.status, _header_delay(exc.headers or {})
            )
        return _by_status(exc.status)

    if isinstance(
        exc,
        (
            httpx.TransportError,
            aiohttp.ClientConnectionError,
            asyncio.TimeoutError,
            TimeoutError,
        ),
    ):
        return Classification('transient')

    return None


def _by_status(status: Optional[int]) -> Classification:
    if status is not None and (status >= 500 or status == 408):
        return Classification('transient', status)
    return Classification('fatal', status)


def _header_delay(headers: Mapping[str, str]) -> Optional[float]:
    """Seconds from ``retry-after-ms`` or ``retry-after`` (seconds or HTTP-date)."""
    try:
        ms = headers.get('retry-after-ms')
        if ms is not None:
            return max(0.0, float(ms) / 1000)
    except (TypeError, ValueError):
        pass

    value = headers.get('retry-after')
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def _gemini_error_details(details: Any) -> list:
    if not isinstance(details, dict):
        return []
    entries = details.get('error', {}).get('details', [])
    return [entry for entry in entries if isinstance(entry, dict)]


def _gemini_retry_delay(details: Any) -> Optional[float]:
    for entry in _gemini_error_details(details):
        if str(entry.get('@type', '')).endswith('RetryInfo'):
            delay = str(entry.get('retryDelay', '')).rstrip('s')
            try:
                return max(0.0, float(delay))
            except ValueError:
                return None
    return None


def _gemini_daily_quota(details: Any) -> bool:
    for entry in _gemini_error_details(details):
        if str(entry.get('@type', '')).endswith('QuotaFailure'):
            for violation in entry.get('violations', []) or []:
                if 'PerDay' in str(violation.get('quotaId', '')):
                    return True
    return False


def _parse_option(name: str, value: Any, whole: bool) -> float:
    """``value`` as a non-negative number, whole when ``whole``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = math.nan
    if (
        isinstance(value, bool)
        or not math.isfinite(number)
        or number < 0
        or (whole and not number.is_integer())
    ):
        kind = 'whole number' if whole else 'number'
        raise ValueError(f'{name} must be a non-negative {kind}, got {value!r}')
    return int(number) if whole else number


def _resolve(value: Any, env_name: str, default: float, whole: bool) -> float:
    if value is not None:
        return value
    raw = os.environ.get(env_name, '').strip()
    return _parse_option(env_name, raw, whole) if raw else default


def apply_rate_limit_options(llm: Any, parameters: Optional[Mapping[str, Any]]) -> None:
    """Set ``llm``'s rate-limit options from an LLM inference config's parameters.

    Only keys present and non-null are applied; the rest keep falling back to
    the env vars and defaults. The caller must also keep ``RATE_LIMIT_OPTIONS``
    out of the provider's request params.
    """
    for name, whole in _OPTION_IS_WHOLE.items():
        value = (parameters or {}).get(name)
        if value is not None:
            setattr(llm, name, _parse_option(name, value, whole))


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


_gates: Dict[Tuple[Any, ...], RateLimitGate] = {}


def get_gate(scope: Tuple[Any, ...]) -> RateLimitGate:
    gate = _gates.get(scope)
    if gate is None:
        gate = _gates[scope] = RateLimitGate()
    return gate


class _Stall:
    """One call's progress through the gate and its stall budget."""

    def __init__(self, llm: Any, provider: str):
        self.provider = provider
        self.model = getattr(llm, 'model', '') or ''
        self.gate = get_gate(llm.rate_limit_scope())
        self.budget = float(
            _resolve(
                llm.rate_limit_max_wait,
                MAX_WAIT_ENV,
                DEFAULT_RATE_LIMIT_MAX_WAIT,
                whole=False,
            )
        )
        self.retries = int(
            _resolve(
                llm.rate_limit_retries,
                RETRIES_ENV,
                DEFAULT_RATE_LIMIT_RETRIES,
                whole=True,
            )
        )
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


def rate_limited(provider: str) -> Callable:
    """Stall a provider's ``generate`` on rate limits and type its failures."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            stall = _Stall(self, provider)
            while True:
                await stall.wait_turn()
                try:
                    return await func(self, *args, **kwargs)
                except Exception as e:
                    info = classify(e)
                    if info is None:
                        raise
                    await stall.absorb(e, info)

        return wrapper

    return decorator


def rate_limited_stream(provider: str) -> Callable:
    """``rate_limited`` for ``stream``; retries only before the first chunk."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            stall = _Stall(self, provider)
            while True:
                await stall.wait_turn()
                started = False
                try:
                    async for chunk in func(self, *args, **kwargs):
                        started = True
                        yield chunk
                    return
                except Exception as e:
                    info = classify(e)
                    if info is None:
                        raise
                    # Once chunks reached the consumer a retry would repeat
                    # them; a rate limit still extends the gate for others.
                    await stall.absorb(e, info, retry=not started)
                    if started:
                        raise LLMRateLimited(
                            f'{provider} rate-limited after streaming began: {e}',
                            provider=provider,
                            status=info.status,
                            retry_after=info.retry_after,
                            original_error=e,
                        ) from e

        return wrapper

    return decorator
