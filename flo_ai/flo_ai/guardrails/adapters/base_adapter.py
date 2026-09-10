"""Abstract base for guardrail safety providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..contracts import (
    AssessmentRequest,
    AssessmentStatus,
    CheckResult,
    FailureClass,
    PolicyAction,
)


class BaseAdapter(ABC):
    """One safety provider, translated into neutral contracts.

    Implementations must not raise for an ordinary "cannot evaluate this"
    outcome — return a ``CheckResult`` with ``AssessmentStatus.ERROR`` and the
    right ``FailureClass`` instead, so the engine can apply the correct
    failure policy. Exceptions that do escape are treated as infrastructure
    failures by the engine.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier, matched against the policy's adapter names."""

    @abstractmethod
    async def evaluate(self, request: AssessmentRequest) -> CheckResult:
        """Evaluate a payload and return a finding."""

    async def aclose(self) -> None:
        """Release any provider resources.

        Default is a no-op; adapters holding network clients override it. The
        engine calls this for every registered adapter on shutdown.
        """
        return None

    # -- helpers for subclasses ------------------------------------------

    def _allow(self, **kwargs: Any) -> CheckResult:
        return CheckResult(
            status=AssessmentStatus.PASS,
            action=PolicyAction.ALLOW,
            adapter=self.name,
            **kwargs,
        )

    def _error(
        self,
        failure_class: FailureClass,
        message: str,
        finding_code: Optional[str] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckResult:
        """An inconclusive result. The engine decides whether it is fatal.

        ``action`` is deliberately BLOCK: the engine downgrades it to ALLOW
        only where the policy permits fail-open for this failure class, so a
        new code path that forgets to consult the policy fails safe.
        """
        return CheckResult(
            status=AssessmentStatus.ERROR,
            action=PolicyAction.BLOCK,
            adapter=self.name,
            failure_class=failure_class,
            finding_code=finding_code,
            message=message,
            provider_metadata=provider_metadata or {},
        )
