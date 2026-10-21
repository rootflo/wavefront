"""Abstract base for guardrail safety providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional

from ..contracts import (
    AssessmentRequest,
    AssessmentStatus,
    CheckResult,
    FailureClass,
    PolicyAction,
    StreamCapability,
)


class BaseAdapter(ABC):
    """One safety provider, translated into neutral contracts.

    Implementations must not raise for an ordinary "cannot evaluate this"
    outcome — return a ``CheckResult`` with ``AssessmentStatus.ERROR`` and the
    right ``FailureClass`` instead, so the engine can apply the correct
    failure policy. Exceptions that do escape are treated as infrastructure
    failures by the engine.
    """

    #: Whether this provider's findings are span-local, and so whether a
    #: guarded stream may release text before the response is complete.
    #:
    #: Defaults to BUFFERED, which is the answer that is never unsafe. An
    #: adapter written against an older version of this class, or by someone
    #: who never read this attribute, inherits the conservative behaviour
    #: rather than silently acquiring permission to leak a prefix.
    stream_capability: ClassVar[StreamCapability] = StreamCapability.BUFFERED

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier, matched against the policy's adapter names."""

    @abstractmethod
    async def evaluate(self, request: AssessmentRequest) -> CheckResult:
        """Evaluate a payload and return a finding."""

    def stream_capability_for(self, options: Dict[str, Any]) -> StreamCapability:
        """Capability under one policy's options, defaulting to the class's.

        Separate from the class attribute because capability is not always a
        property of the provider alone. Presidio's findings are span-local for
        a credit card and emphatically not for a person's name, and the class
        attribute cannot see which of the two a policy selected.

        Sync and side-effect-free: the engine calls this while deciding how to
        run a stream, before the provider has been asked anything.
        """
        return self.stream_capability

    async def warmup(self) -> None:
        """Build whatever the first evaluation would otherwise build.

        Default is a no-op; adapters with expensive lazy state override it.

        Exists because that state is otherwise built inside a call the engine
        has already put a timeout on — ``AdapterSpec.timeout_seconds``, which
        is sized for checking a message rather than for loading a model. An
        adapter whose first call has to load one blows that budget, reports a
        timeout, and under a FAIL_CLOSED policy rejects the request. The cost
        does not disappear; it moves to startup, where nothing is waiting on
        it and no caller is refused because of it.
        """
        return None

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
