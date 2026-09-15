"""Provider-neutral contracts for the guardrails framework.

Nothing in this module imports a safety provider. Adapters translate these
neutral shapes into Azure/Presidio/whatever calls, so the engine and the
``GuardedLLM`` interceptor never learn a vendor's JSON shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


class WorkflowStage(str, Enum):
    """Point in the agent loop at which a payload is evaluated."""

    BEFORE_MODEL = 'BEFORE_MODEL'
    AFTER_MODEL = 'AFTER_MODEL'
    # Phase 2. Declared here so policies can be authored against them before
    # the tool interceptor exists; the engine rejects them until then.
    BEFORE_TOOL = 'BEFORE_TOOL'
    AFTER_TOOL = 'AFTER_TOOL'


class PolicyAction(str, Enum):
    """What a check wants done with the payload."""

    ALLOW = 'ALLOW'
    BLOCK = 'BLOCK'
    TRANSFORM = 'TRANSFORM'


class EnforcementMode(str, Enum):
    """Whether a policy's verdicts are acted on.

    ``MONITOR`` evaluates and records exactly as ``ENFORCE`` does but never
    blocks or rewrites, so a policy can be rolled out against live traffic to
    measure its false-positive rate before it can break anything.
    """

    MONITOR = 'MONITOR'
    ENFORCE = 'ENFORCE'


class FailureMode(str, Enum):
    """What to do when an adapter cannot return a verdict."""

    FAIL_OPEN = 'FAIL_OPEN'
    FAIL_CLOSED = 'FAIL_CLOSED'


class FailureClass(str, Enum):
    """Why an adapter failed, which determines whether fail-open is allowed.

    The distinction matters because these are not equally trustworthy. An
    outage is something the provider does to you at random; oversized or
    wrongly-typed content is something the *caller* chooses, so honouring
    ``FAIL_OPEN`` there would hand anyone a bypass they can trigger on demand.
    """

    NONE = 'NONE'
    #: Provider unreachable, timed out, or rate-limited. Policy decides.
    INFRASTRUCTURE = 'INFRASTRUCTURE'
    #: Adapter refused the payload (too long, unsupported type). Always closed.
    INPUT_REJECTED = 'INPUT_REJECTED'
    #: Policy names an adapter that is not registered. Always closed.
    MISCONFIGURED = 'MISCONFIGURED'


class AssessmentStatus(str, Enum):
    """Outcome of a single adapter's evaluation."""

    PASS = 'PASS'
    VIOLATION = 'VIOLATION'
    INCONCLUSIVE = 'INCONCLUSIVE'
    ERROR = 'ERROR'


@dataclass(frozen=True)
class Principal:
    """Identity a ``GuardedLLM`` is bound to when it is constructed.

    Deliberately not a per-call argument. Policy that depends on the caller
    remembering to pass a context is policy that silently lapses the first
    time someone forgets, and every call site that forgets becomes a bypass.
    """

    namespace: Optional[str] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass(frozen=True)
class AdapterSpec:
    """One adapter as configured by the active policy."""

    name: str
    stages: Tuple[WorkflowStage, ...]
    on_error: FailureMode = FailureMode.FAIL_OPEN
    timeout_seconds: float = 5.0
    #: Adapter-specific tuning (thresholds, entity allowlists, ...).
    options: Dict[str, Any] = field(default_factory=dict)

    def applies_to(self, stage: WorkflowStage) -> bool:
        return stage in self.stages


@dataclass(frozen=True)
class ResolvedPolicy:
    """The effective policy for a principal, as returned by a resolver."""

    is_enabled: bool = False
    mode: EnforcementMode = EnforcementMode.MONITOR
    adapters: Tuple[AdapterSpec, ...] = ()
    version: Optional[str] = None

    #: A policy that is off, or that configures nothing, has no work to do.
    def adapters_for(self, stage: WorkflowStage) -> Tuple[AdapterSpec, ...]:
        if not self.is_enabled:
            return ()
        return tuple(spec for spec in self.adapters if spec.applies_to(stage))


DISABLED_POLICY = ResolvedPolicy(is_enabled=False)


@runtime_checkable
class PolicyResolver(Protocol):
    """Port for loading the active policy for a principal.

    Implemented in the SDK by ``StaticPolicyResolver`` and in the server by a
    database/cache-backed resolver, so ``flo_ai`` never depends on storage.
    """

    async def resolve(self, principal: Principal) -> ResolvedPolicy: ...


@dataclass(frozen=True)
class EvaluationContext:
    """Per-evaluation context, derived from a ``Principal`` plus the stage."""

    workflow_stage: WorkflowStage
    principal: Principal = field(default_factory=Principal)
    run_id: Optional[str] = None
    destination: Optional[str] = None
    policy_version: Optional[str] = None

    @property
    def namespace(self) -> Optional[str]:
        return self.principal.namespace

    @property
    def agent_id(self) -> Optional[str]:
        return self.principal.agent_id

    @property
    def user_id(self) -> Optional[str]:
        return self.principal.user_id


@dataclass
class AssessmentRequest:
    """A single payload handed to an adapter."""

    context: EvaluationContext
    content: Any
    #: Set by the engine so an adapter can read its own policy options.
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    """One adapter's verdict."""

    status: AssessmentStatus
    action: PolicyAction
    adapter: Optional[str] = None
    finding_code: Optional[str] = None
    message: Optional[str] = None
    transformed_content: Optional[Any] = None
    #: Only meaningful when ``status`` is ERROR.
    failure_class: FailureClass = FailureClass.NONE
    #: Highest provider severity seen, normalised 0.0-1.0 where comparable.
    severity: Optional[float] = None
    #: Never put raw evaluated content in here; it gets logged and persisted.
    provider_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_error(self) -> bool:
        return self.status is AssessmentStatus.ERROR


@dataclass
class PolicyDecision:
    """The engine's aggregate verdict for one payload."""

    action: PolicyAction = PolicyAction.ALLOW
    results: List[CheckResult] = field(default_factory=list)
    transformed_content: Optional[Any] = None
    #: False when the policy ran in MONITOR mode, i.e. ``action`` is advisory.
    enforced: bool = True
    #: What the policy *would* have done, always populated even in monitor mode.
    observed_action: PolicyAction = PolicyAction.ALLOW
    policy_version: Optional[str] = None

    @property
    def blocked(self) -> bool:
        return self.enforced and self.action is PolicyAction.BLOCK

    @property
    def transformed(self) -> bool:
        return (
            self.enforced
            and self.action is PolicyAction.TRANSFORM
            and self.transformed_content is not None
        )

    def block_reasons(self) -> List[str]:
        """Full detail for operators: logs, audit rows, debugging.

        Names adapters and finding codes, so this is **not** for end users.
        See ``caller_message``.
        """
        reasons = [
            result.message
            for result in self.results
            if result.action is PolicyAction.BLOCK and result.message
        ]
        return reasons or ['Blocked by guardrail policy']

    def caller_message(self, subject: str = 'request') -> str:
        """A single message safe to show the end user.

        Deliberately names no adapter, threshold or finding code. Those
        describe which checks run and how they are tuned, which is a map of
        how to get around them — the API that manages this policy is
        admin-only for that exact reason, so the enforcement path must not
        hand the same detail to anyone who trips it.

        It does distinguish the cases a caller can act on, because "your input
        was rejected" and "our safety config is broken" need opposite
        responses from whoever reads it.
        """
        blocking = [r for r in self.results if r.action is PolicyAction.BLOCK]

        if any(r.failure_class is FailureClass.MISCONFIGURED for r in blocking):
            return (
                'Safety checks are not correctly configured for this '
                'workspace, so nothing was sent to the model. This is not a '
                'problem with your input — please contact your administrator.'
            )
        if any(r.failure_class is FailureClass.INFRASTRUCTURE for r in blocking):
            return (
                'Safety checks could not be completed just now, so nothing '
                'was sent to the model. Please try again shortly.'
            )
        if any(r.failure_class is FailureClass.INPUT_REJECTED for r in blocking):
            return (
                f'This {subject} could not be checked for safety, so it was '
                f'not processed. It may be too large or in an unsupported '
                f'format.'
            )
        if any((r.finding_code or '').startswith('privacy.') for r in blocking):
            return (
                f'This {subject} was blocked because it appears to contain '
                f'personal or sensitive information.'
            )
        return f'This {subject} was blocked by a content safety policy.'
