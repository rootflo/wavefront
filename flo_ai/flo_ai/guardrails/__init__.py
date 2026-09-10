"""Provider-neutral AI guardrails.

Importing this package pulls in no safety provider. Adapters live in
``flo_ai.guardrails.adapters`` and import their SDKs lazily, so a deployment
that uses only Presidio never needs the Azure package installed.
"""

from .contracts import (
    DISABLED_POLICY,
    AdapterSpec,
    AssessmentRequest,
    AssessmentStatus,
    CheckResult,
    EnforcementMode,
    EvaluationContext,
    FailureClass,
    FailureMode,
    PolicyAction,
    PolicyDecision,
    PolicyResolver,
    Principal,
    ResolvedPolicy,
    WorkflowStage,
)
from .engine import AuditSink, GuardrailsEngine, StaticPolicyResolver
from .run_context import get_run_id, run_scope

__all__ = [
    'DISABLED_POLICY',
    'AdapterSpec',
    'AssessmentRequest',
    'AssessmentStatus',
    'AuditSink',
    'CheckResult',
    'EnforcementMode',
    'EvaluationContext',
    'FailureClass',
    'FailureMode',
    'GuardrailsEngine',
    'PolicyAction',
    'PolicyDecision',
    'PolicyResolver',
    'Principal',
    'ResolvedPolicy',
    'StaticPolicyResolver',
    'WorkflowStage',
    'get_run_id',
    'run_scope',
]
