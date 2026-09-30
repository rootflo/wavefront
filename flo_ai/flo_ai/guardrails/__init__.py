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
from .verdict_cache import (
    SCHEMA_VERSION,
    VERDICT_CACHE_CHAR_BUDGET,
    LocalVerdictCache,
    NullVerdictCache,
    TieredVerdictCache,
    VerdictCache,
    build_local_cache,
    carries_content,
    decode_decision,
    encode_decision,
)

__all__ = [
    'DISABLED_POLICY',
    'SCHEMA_VERSION',
    'VERDICT_CACHE_CHAR_BUDGET',
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
    'LocalVerdictCache',
    'NullVerdictCache',
    'PolicyAction',
    'PolicyDecision',
    'PolicyResolver',
    'Principal',
    'ResolvedPolicy',
    'StaticPolicyResolver',
    'TieredVerdictCache',
    'VerdictCache',
    'WorkflowStage',
    'build_local_cache',
    'carries_content',
    'decode_decision',
    'encode_decision',
    'get_run_id',
    'run_scope',
]
