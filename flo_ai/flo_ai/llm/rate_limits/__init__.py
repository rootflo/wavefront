"""Provider error typing and rate-limit stalling at the LLM boundary.

``@rate_limited`` / ``@rate_limited_stream`` wrap a provider's ``generate`` /
``stream``. Errors are typed there, where only the LLM call is in scope, so a
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

Every caller sharing a ``RateLimitScope`` shares one ``RateLimitGate``, so a 429
seen by one call pauses all of them.

Known costs:

- Calls already in flight when a 429 arrives don't consult the gate.
- The budget is checked between attempts, so a call can overrun it by one
  request's duration.
- The budget is per LLM call. An agent run makes several calls, so its worst
  case stall is a multiple of it.
- ``rate_limit_max_wait=0`` disables retries: a 429 or transient failure is
  raised at once, and a call fails immediately while another caller has the
  gate cooling down.

Layout: ``models`` (plain data), ``errors``, ``options`` (budget and retry
settings), ``providers/`` (one classifier per SDK), ``classifier``, ``gate``,
``stall`` (one call's waits) and ``decorators``.
"""

from flo_ai.llm.rate_limits.classifier import classify
from flo_ai.llm.rate_limits.decorators import rate_limited, rate_limited_stream
from flo_ai.llm.rate_limits.errors import LLMProviderError, LLMRateLimited
from flo_ai.llm.rate_limits.gate import RateLimitGate, get_gate
from flo_ai.llm.rate_limits.models import Classification, RateLimitScope
from flo_ai.llm.rate_limits.options import (
    DEFAULT_RATE_LIMIT_MAX_WAIT,
    DEFAULT_RATE_LIMIT_RETRIES,
    MAX_WAIT_ENV,
    RATE_LIMIT_OPTIONS,
    RETRIES_ENV,
    apply_rate_limit_options,
)

__all__ = [
    'Classification',
    'DEFAULT_RATE_LIMIT_MAX_WAIT',
    'DEFAULT_RATE_LIMIT_RETRIES',
    'LLMProviderError',
    'LLMRateLimited',
    'MAX_WAIT_ENV',
    'RATE_LIMIT_OPTIONS',
    'RETRIES_ENV',
    'RateLimitGate',
    'RateLimitScope',
    'apply_rate_limit_options',
    'classify',
    'get_gate',
    'rate_limited',
    'rate_limited_stream',
]
