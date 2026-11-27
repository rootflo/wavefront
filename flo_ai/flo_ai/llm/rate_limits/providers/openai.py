"""OpenAI SDK failures, which also cover Azure OpenAI, vLLM and RootFlo."""

from typing import Optional

import openai

from flo_ai.llm.rate_limits.models import Classification
from flo_ai.llm.rate_limits.providers.common import classify_sdk_status_error


def classify_openai_error(exc: BaseException) -> Optional[Classification]:
    if isinstance(exc, openai.APIStatusError):
        return classify_sdk_status_error(exc)
    if isinstance(exc, openai.APIConnectionError):
        return Classification('transient')
    return None
