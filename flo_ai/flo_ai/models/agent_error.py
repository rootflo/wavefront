from typing import Optional


class AgentError(Exception):
    """Base exception for agent errors"""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error
