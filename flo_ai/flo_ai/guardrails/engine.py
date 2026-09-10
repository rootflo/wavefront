"""Policy resolution and adapter orchestration."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from flo_ai.utils.logger import logger

from .adapters.base_adapter import BaseAdapter
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
    Principal,
    ResolvedPolicy,
    WorkflowStage,
)
from .run_context import get_run_id

#: Stages the interceptor implements today. Policies may reference the Phase 2
#: tool stages, but routing a payload to them would silently do nothing, so the
#: engine treats them as a misconfiguration rather than pretending to check.
SUPPORTED_STAGES = (WorkflowStage.BEFORE_MODEL, WorkflowStage.AFTER_MODEL)


class AuditSink(Protocol):
    """Durable record of enforcement decisions.

    Receives findings, never raw evaluated content: the point of a guardrail
    is to keep sensitive payloads from spreading, and an audit log that copies
    them defeats it.
    """

    async def record(
        self, decision: PolicyDecision, context: EvaluationContext
    ) -> None: ...


class StaticPolicyResolver:
    """Returns one fixed policy regardless of principal.

    For tests and single-tenant embedding. The server ships a resolver backed
    by the policy table and a cache.
    """

    def __init__(self, policy: ResolvedPolicy) -> None:
        self._policy = policy

    async def resolve(self, principal: Principal) -> ResolvedPolicy:
        return self._policy


class GuardrailsEngine:
    """Routes a payload to the adapters the active policy asks for."""

    def __init__(
        self,
        resolver: Optional[Any] = None,
        adapters: Optional[Sequence[BaseAdapter]] = None,
        audit_sink: Optional[AuditSink] = None,
    ) -> None:
        # No resolver means no policy, which means nothing is enabled. A
        # guardrails engine that enforces by default would surprise every
        # caller that constructed one without configuring it.
        self._resolver = resolver or StaticPolicyResolver(DISABLED_POLICY)
        self._adapters: Dict[str, BaseAdapter] = {}
        self._audit_sink = audit_sink
        for adapter in adapters or ():
            self.register_adapter(adapter)

    def register_adapter(self, adapter: BaseAdapter) -> None:
        """Register an adapter under its own declared name.

        The name is taken from the adapter rather than supplied by the caller;
        letting them diverge means a policy naming ``presidio_pii`` could
        silently be served by something else.
        """
        self._adapters[adapter.name] = adapter

    @property
    def registered(self) -> Tuple[str, ...]:
        return tuple(sorted(self._adapters))

    async def aclose(self) -> None:
        """Release every adapter's resources."""
        for adapter in self._adapters.values():
            try:
                await adapter.aclose()
            except Exception as exc:  # pragma: no cover - shutdown best effort
                logger.warning(
                    f'Guardrail adapter {adapter.name} failed to close: {exc}'
                )

    async def has_checks(self, principal: Principal, stage: WorkflowStage) -> bool:
        """Whether the active policy evaluates anything at ``stage``.

        Lets a caller adapt before spending the call — ``GuardedLLM`` uses it
        to decide whether a stream has to be collected before release.
        """
        policy = await self._resolve(principal)
        return bool(policy.adapters_for(stage))

    async def evaluate(
        self,
        content: Any,
        principal: Principal,
        stage: WorkflowStage,
        destination: Optional[str] = None,
    ) -> PolicyDecision:
        """Evaluate ``content`` for ``principal`` at ``stage``."""
        policy = await self._resolve(principal)
        specs = policy.adapters_for(stage)
        context = EvaluationContext(
            workflow_stage=stage,
            principal=principal,
            run_id=get_run_id(),
            destination=destination,
            policy_version=policy.version,
        )

        if not specs:
            return PolicyDecision(policy_version=policy.version)

        results = await self._run_adapters(content, context, specs)
        decision = await self._decide(content, results, policy, context, specs)
        await self._audit(decision, context)
        return decision

    # -- policy ----------------------------------------------------------

    async def _resolve(self, principal: Principal) -> ResolvedPolicy:
        try:
            return await self._resolver.resolve(principal)
        except Exception as exc:
            # A resolver outage must not silently disable enforcement, but it
            # also must not take the product down. Log loudly and treat it as
            # disabled; the ERROR metric on this path is what alerting watches.
            logger.error(
                f'Guardrail policy resolution failed for {principal}: {exc}',
                exc_info=exc,
            )
            return DISABLED_POLICY

    # -- adapter execution -----------------------------------------------

    async def _run_adapters(
        self,
        content: Any,
        context: EvaluationContext,
        specs: Sequence[AdapterSpec],
    ) -> List[CheckResult]:
        tasks = [self._run_one(content, context, spec) for spec in specs]
        return list(await asyncio.gather(*tasks))

    async def _run_one(
        self,
        content: Any,
        context: EvaluationContext,
        spec: AdapterSpec,
    ) -> CheckResult:
        if context.workflow_stage not in SUPPORTED_STAGES:
            return self._misconfigured(
                spec, f'Stage {context.workflow_stage.value} is not implemented'
            )

        adapter = self._adapters.get(spec.name)
        if adapter is None:
            # A typo in a policy must not read as "no checks required".
            return self._misconfigured(
                spec,
                f"Adapter '{spec.name}' is configured but not registered "
                f'(registered: {", ".join(self.registered) or "none"})',
            )

        request = AssessmentRequest(
            context=context, content=content, options=dict(spec.options)
        )
        try:
            result = await asyncio.wait_for(
                adapter.evaluate(request), timeout=spec.timeout_seconds
            )
        except asyncio.TimeoutError:
            result = CheckResult(
                status=AssessmentStatus.ERROR,
                action=PolicyAction.BLOCK,
                adapter=spec.name,
                failure_class=FailureClass.INFRASTRUCTURE,
                finding_code='guardrail.timeout',
                message=f'{spec.name} timed out after {spec.timeout_seconds}s',
            )
        except Exception as exc:
            logger.error(f'Guardrail adapter {spec.name} raised: {exc}', exc_info=exc)
            result = CheckResult(
                status=AssessmentStatus.ERROR,
                action=PolicyAction.BLOCK,
                adapter=spec.name,
                failure_class=FailureClass.INFRASTRUCTURE,
                finding_code='guardrail.adapter_error',
                message=str(exc),
            )

        result.adapter = result.adapter or spec.name
        return self._apply_failure_mode(result, spec)

    def _misconfigured(self, spec: AdapterSpec, message: str) -> CheckResult:
        logger.error(f'Guardrail policy misconfiguration: {message}')
        return CheckResult(
            status=AssessmentStatus.ERROR,
            action=PolicyAction.BLOCK,
            adapter=spec.name,
            failure_class=FailureClass.MISCONFIGURED,
            finding_code='guardrail.misconfigured',
            message=message,
        )

    @staticmethod
    def _apply_failure_mode(result: CheckResult, spec: AdapterSpec) -> CheckResult:
        """Downgrade an error to ALLOW only where the policy permits it.

        Adapters report errors as BLOCK; fail-open is granted here and only
        for infrastructure failures. Input rejections and misconfigurations
        stay closed no matter what the policy says, because both are reachable
        by the caller and would otherwise be a bypass on demand.
        """
        if not result.is_error:
            return result
        if result.failure_class is not FailureClass.INFRASTRUCTURE:
            return result
        if spec.on_error is FailureMode.FAIL_OPEN:
            result.action = PolicyAction.ALLOW
        return result

    # -- aggregation -----------------------------------------------------

    async def _decide(
        self,
        content: Any,
        results: List[CheckResult],
        policy: ResolvedPolicy,
        context: EvaluationContext,
        specs: Sequence[AdapterSpec],
    ) -> PolicyDecision:
        observed = PolicyAction.ALLOW
        transformed: Optional[Any] = None

        if any(r.action is PolicyAction.BLOCK for r in results):
            observed = PolicyAction.BLOCK
        else:
            transformers = [
                r
                for r in results
                if r.action is PolicyAction.TRANSFORM
                and r.transformed_content is not None
            ]
            if transformers:
                observed = PolicyAction.TRANSFORM
                transformed = await self._compose(content, context, specs, transformers)

        enforced = policy.mode is EnforcementMode.ENFORCE
        if enforced:
            action = observed
        else:
            # Monitor mode records the verdict and lets the payload through.
            action = PolicyAction.ALLOW
            if observed is not PolicyAction.ALLOW:
                logger.info(
                    f'Guardrail (monitor) would have {observed.value} at '
                    f'{context.workflow_stage.value} for agent '
                    f'{context.agent_id or "-"}'
                )

        return PolicyDecision(
            action=action,
            results=results,
            transformed_content=transformed if enforced else None,
            enforced=enforced,
            observed_action=observed,
            policy_version=policy.version,
        )

    async def _compose(
        self,
        content: Any,
        context: EvaluationContext,
        specs: Sequence[AdapterSpec],
        transformers: List[CheckResult],
    ) -> Any:
        """Combine multiple adapters' rewrites of the same payload.

        Every adapter evaluated the *original* content concurrently, so their
        rewrites cannot be stacked: taking the last one silently discards the
        others' redactions, which is how a payload ends up leaving with the
        SSN scrubbed but the email intact.

        With one transformer — the common case, since only PII adapters
        rewrite — its output is authoritative and nothing extra runs. With
        several, they are re-run as a chain so each sees its predecessor's
        output. That costs one extra call per additional transformer, on a
        path that only triggers when two adapters both want to rewrite the
        same payload.
        """
        if len(transformers) == 1:
            return transformers[0].transformed_content

        rewrote = {t.adapter for t in transformers}
        current = content
        for index, spec in enumerate(s for s in specs if s.name in rewrote):
            if index == 0:
                # The first adapter already saw the original content, so its
                # existing verdict stands; re-running it would be identical.
                result = next(t for t in transformers if t.adapter == spec.name)
            else:
                result = await self._run_one(current, context, spec)
            if (
                result.action is PolicyAction.TRANSFORM
                and result.transformed_content is not None
            ):
                current = result.transformed_content
        return current

    # -- audit -----------------------------------------------------------

    async def _audit(
        self, decision: PolicyDecision, context: EvaluationContext
    ) -> None:
        if self._audit_sink is None:
            return
        if decision.observed_action is PolicyAction.ALLOW and not any(
            r.is_error for r in decision.results
        ):
            return
        try:
            await self._audit_sink.record(decision, context)
        except Exception as exc:
            # Losing an audit row must not fail the request it describes.
            logger.error(f'Guardrail audit sink failed: {exc}', exc_info=exc)
