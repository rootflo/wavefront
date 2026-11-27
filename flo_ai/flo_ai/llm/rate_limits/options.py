"""How long one call may stall on rate limits, and how many times it may retry.

Both are LLM attributes. Unset (None), each falls back to its
``FLO_AI_RATE_LIMIT_*`` env var, read when a call starts, then to the default
here. An LLM inference config can set them through its ``parameters``; see
``apply_rate_limit_options``.
"""

import math
import os
from typing import Any, Mapping, Optional

DEFAULT_RATE_LIMIT_MAX_WAIT = 60.0
# A short Retry-After would otherwise allow dozens of requests per budget.
DEFAULT_RATE_LIMIT_RETRIES = 4
MAX_WAIT_ENV = 'FLO_AI_RATE_LIMIT_MAX_WAIT'
RETRIES_ENV = 'FLO_AI_RATE_LIMIT_RETRIES'
# Keys an LLM inference config's parameters may carry for this layer, and
# whether each must be whole. Never request params: providers reject them.
_OPTION_IS_WHOLE = {'rate_limit_max_wait': False, 'rate_limit_retries': True}
RATE_LIMIT_OPTIONS = frozenset(_OPTION_IS_WHOLE)


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


def resolve_max_wait(llm: Any) -> float:
    """Seconds ``llm``'s calls may stall on rate limits."""
    return float(
        _resolve(
            llm.rate_limit_max_wait,
            MAX_WAIT_ENV,
            DEFAULT_RATE_LIMIT_MAX_WAIT,
            whole=False,
        )
    )


def resolve_retries(llm: Any) -> int:
    """Times one of ``llm``'s calls may retry a rate limit."""
    return int(
        _resolve(
            llm.rate_limit_retries,
            RETRIES_ENV,
            DEFAULT_RATE_LIMIT_RETRIES,
            whole=True,
        )
    )


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
