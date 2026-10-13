from typing import Optional


class AgentError(Exception):
    """Base exception for agent errors"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class ModelRefusedError(AgentError):
    """The model declined the request (a provider safety refusal).

    ``retryable`` is False: the same request gets the same refusal, so it is
    reported as it is and not analysed and retried.
    """

    retryable = False

    def __init__(
        self,
        message: str,
        category: Optional[str] = None,
        explanation: Optional[str] = None,
    ):
        super().__init__(message)
        self.category = category
        self.explanation = explanation
