"""The errors a provider call raises once this layer has given up on it."""

from typing import Optional

from flo_ai.models.agent_error import AgentError


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
