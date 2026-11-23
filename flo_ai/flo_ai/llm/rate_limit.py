"""Provider error typing and rate-limit stalling at the LLM boundary.

``@rate_limited`` / ``@rate_limited_stream`` wrap a provider's ``generate`` /
``stream``. Errors are typed here, where only the LLM call is in scope, so a
tool's own httpx failure is never mistaken for a provider failure upstream:

- a 429 (or Anthropic 529) stalls the call, honouring Retry-After, and retries
  until ``llm.rate_limit_max_wait`` seconds have passed; then
  ``LLMRateLimited`` is raised
- any other recognised provider failure becomes ``LLMProviderError`` with
  ``transient`` set for 5xx / 408 / timeout / connection errors
- anything unrecognised propagates untouched

Every caller sharing a provider, endpoint, model and key shares one
``RateLimitGate``, so a 429 seen by one call pauses all of them. The gate is
per process: each worker and pod has its own.

Known costs:

- SDK retries stay on (OpenAI/Anthropic 2x, boto3 default), so up to three
  requests hit the provider before the gate learns of a 429, and calls
  already in flight don't consult it.
- For a 5xx, retries stack: 3 SDK attempts x (1 + agent ``max_retries``) is
  up to ~12 requests at the default of 3.
- The budget is per LLM call. An agent run makes several calls, so its worst
  case stall is a multiple of it.
- ``rate_limit_max_wait=0`` never retries a 429, and fails immediately while
  another caller has the gate cooling down.
"""

import asyncio
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
MAX_BACKOFF = 30.0
WAKE_JITTER = 1.0

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


async def provider_retry_sleep(attempt: int) -> None:
    """The agent's pause before re-trying a transient provider error."""
    await asyncio.sleep(min(MAX_BACKOFF, 2 ** (attempt - 1)))


class _Stall:
    """One call's progress through the gate and its stall budget."""

    def __init__(self, llm: Any, provider: str):
        self.provider = provider
        self.model = getattr(llm, 'model', '') or ''
        self.gate = get_gate(llm.rate_limit_scope())
        self.budget = max(0.0, float(llm.rate_limit_max_wait))
        self.started = self.gate.clock()
        self.attempt = 0
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
            message = (
                f'{self.provider} rate limit persisted for {waited:.0f}s '
                f'(budget {self.budget:.0f}s): {error}'
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
            left = self._left()
            if remaining > left:
                error = self.last[0] if self.last else None
                raise self._exhausted() from error
            wait = min(remaining + self.gate.rand(0, WAKE_JITTER), left)
            await self.gate.sleep(wait)
            llm_metrics.record_rate_limit_wait(wait * 1000, self.model, self.provider)

    def absorb(self, error: Exception, info: Classification) -> None:
        """Take a rate limit onto the gate, or raise the typed error."""
        if info.kind != 'rate_limit':
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
        if self.attempt == 0:
            logger.warning(
                f'{self.provider} rate-limited ({info.status}) on {self.model}; '
                f'stalling up to {self.budget:.0f}s'
            )
        self.attempt += 1
        self.last = (error, info)


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
                    stall.absorb(e, info)

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
                    if started and info.kind == 'rate_limit':
                        # Chunks already reached the consumer; a retry would
                        # repeat them. Still extend the gate for other callers.
                        stall.absorb(e, info)
                        raise LLMRateLimited(
                            f'{provider} rate-limited after streaming began: {e}',
                            provider=provider,
                            status=info.status,
                            retry_after=info.retry_after,
                            original_error=e,
                        ) from e
                    stall.absorb(e, info)

        return wrapper

    return decorator
