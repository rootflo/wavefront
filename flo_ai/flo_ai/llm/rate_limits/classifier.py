"""Type a provider failure as a rate limit, a transient failure or a fatal one."""

from typing import Callable, Optional, Tuple

from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.providers.anthropic import classify_anthropic_error
from flo_ai.llm.rate_limits.providers.bedrock import classify_bedrock_error
from flo_ai.llm.rate_limits.providers.gemini import classify_gemini_error
from flo_ai.llm.rate_limits.providers.http import classify_http_error
from flo_ai.llm.rate_limits.providers.openai import classify_openai_error

# Provider SDKs first; plain HTTP and timeouts, which any of them can raise, last.
_CLASSIFIERS: Tuple[Callable[[BaseException], Optional[Classification]], ...] = (
    classify_openai_error,
    classify_anthropic_error,
    classify_gemini_error,
    classify_bedrock_error,
    classify_http_error,
)


def classify(exc: BaseException) -> Optional[Classification]:
    """Type a provider failure, or None when it isn't one.

    Looks at ``__cause__`` too: the Anthropic and Gemini wrappers re-raise as a
    plain Exception ``from`` the SDK error.
    """
    for candidate in (exc, exc.__cause__):
        if candidate is None:
            continue
        for classifier in _CLASSIFIERS:
            result = classifier(candidate)
            if result is not None:
                return result
    return None
