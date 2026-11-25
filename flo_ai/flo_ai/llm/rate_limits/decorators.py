"""The decorators a provider puts on its ``generate`` and ``stream``.

Applied outermost, above the telemetry decorators, so each attempt gets its
own span and the waits stay out of latency metrics.
"""

from functools import wraps
from typing import Callable

from flo_ai.llm.rate_limits.classifier import classify
from flo_ai.llm.rate_limits.errors import LLMRateLimited
from flo_ai.llm.rate_limits.stall import Stall


def rate_limited(provider: str) -> Callable:
    """Stall a provider's ``generate`` on rate limits and type its failures."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            stall = Stall(self, provider)
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
            stall = Stall(self, provider)
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
