"""Anthropic SDK failures."""

from typing import Optional

import anthropic

from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.providers.common import classify_sdk_status_error


def classify_anthropic_error(exc: BaseException) -> Optional[Classification]:
    if isinstance(exc, anthropic.APIStatusError):
        return classify_sdk_status_error(exc)
    if isinstance(exc, anthropic.APIConnectionError):
        return Classification('transient')
    return None
