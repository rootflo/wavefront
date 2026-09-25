"""Policy resolution and adapter orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
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
    StreamCapability,
    StreamMode,
    WorkflowStage,
)
from .run_context import get_run_id
from .verdict_cache import (
    VERDICT_CACHE_CHAR_BUDGET,
    VerdictCache,
    build_local_cache,
)

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
        verdict_cache_chars: int = VERDICT_CACHE_CHAR_BUDGET,
        verdict_cache: Optional[VerdictCache] = None,
        cache_key_secret: Optional[Any] = None,
    ) -> None:
        # No resolver means no policy, which means nothing is enabled. A
        # guardrails engine that enforces by default would surprise every
        # caller that constructed one without configuring it.
        self._resolver = resolver or StaticPolicyResolver(DISABLED_POLICY)
        self._adapters: Dict[str, BaseAdapter] = {}
        self._audit_sink = audit_sink
        # Per instance, not per module: two engines in one process serve
        # different configurations, and one cache would cross them. Callers
        # that want a shared backend pass ``verdict_cache`` (normally a
        # TieredVerdictCache wrapping a local tier); otherwise the local tier
        # stands alone and ``verdict_cache_chars=0`` turns caching off.
        self._verdicts: VerdictCache = verdict_cache or build_local_cache(
            verdict_cache_chars
        )
        self._key_secret = self._coerce_secret(cache_key_secret)

        if verdict_cache is not None and self._key_secret is None:
            # Only worth saying when a backend was supplied, since that is the
            # case where keys leave the process. A bare SHA-256 of short
            # content is brute-forceable: anyone who can read the cache can
            # enumerate every 10-digit number and match digests, which turns
            # the key itself into a disclosure for payloads like a lone phone
            # number or account ID.
            logger.warning(
                'Guardrail verdict cache has a shared backend but no key '
                'secret; cache keys fall back to plain SHA-256, which is '
                'brute-forceable for short payloads. Set a secret to close it.'
            )

        for adapter in adapters or ():
            self.register_adapter(adapter)

    @staticmethod
    def _coerce_secret(secret: Optional[Any]) -> Optional[bytes]:
        if secret is None:
            return None
        if isinstance(secret, bytes):
            return secret or None
        if isinstance(secret, str):
            return secret.encode('utf-8') or None
        raise TypeError('cache_key_secret must be str, bytes or None')

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

    def get_adapter(self, name: str) -> Optional[BaseAdapter]:
        """The registered adapter by name, or ``None``.

        Exposed for callers that need a provider's own capabilities - listing
        the entity types Presidio can detect, say - rather than an evaluation.
        Without it those callers reach into the private registry and break
        whenever it changes.
        """
        return self._adapters.get(name)

    async def warmup(self) -> None:
        """Build every adapter's lazy state before any request needs it.

        Call once at startup. Without it, whichever request is checked first
        pays for a provider's initialisation inside the per-check timeout the
        policy sets — and a FAIL_CLOSED policy turns that into a rejected
        request rather than a slow one.

        A warmup failure is logged and swallowed. It is not a reason to refuse
        to start: the adapter will try again on first use, which is exactly the
        behaviour there was before warming existed. What it must not do is take
        the process down for a provider the policy may not even name.
        """
        for adapter in self._adapters.values():
            started = time.monotonic()
            try:
                await adapter.warmup()
            except Exception as exc:
                logger.warning(
                    f'Guardrail adapter {adapter.name} failed to warm up: {exc}. '
                    f'It will initialise on first use instead, which may time '
                    f'out that request.'
                )
                continue
            # INFO, and timed: this is how you tell a warm process from one
            # that skipped warming and is about to reject its first request.
            # If the number here is larger than the policy's timeout, that
            # cost was previously being charged to a user.
            logger.info(
                f'Guardrail adapter {adapter.name} warmed in '
                f'{time.monotonic() - started:.1f}s'
            )

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

    async def stream_mode(
        self, principal: Principal, stage: WorkflowStage
    ) -> StreamMode:
        """How a guarded stream at ``stage`` may release chunks.

        Strictest wins, and the order of the checks is the policy:

        The tenant's own preference is consulted **last**, so it can only ever
        weaken streaming. An adapter that declares itself BUFFERED has said
        its verdict is not meaningful on a prefix; no tenant setting should be
        able to overrule that, and putting the check last means none can.

        An adapter the policy names but nothing registered returns BUFFERED
        rather than INCREMENTAL. Such a policy fails closed on every request
        (MISCONFIGURED is never eligible for fail-open), so under incremental
        release every single response would be released and then retracted.
        Buffering blocks it cleanly instead, before anything escapes.

        The MONITOR check sits above both, and deliberately: in monitor mode
        nothing is enforced, so the misconfiguration cannot block either, and
        withholding text to protect a verdict nobody will act on is pure cost.
        """
        policy = await self._resolve(principal)
        specs = policy.adapters_for(stage)
        if not specs:
            return StreamMode.PASSTHROUGH
        if stage not in SUPPORTED_STAGES:
            return StreamMode.BUFFERED
        if policy.mode is not EnforcementMode.ENFORCE:
            return StreamMode.OBSERVE

        for spec in specs:
            adapter = self._adapters.get(spec.name)
            if adapter is None:
                return StreamMode.BUFFERED
            if adapter.stream_capability_for(spec.options) is StreamCapability.BUFFERED:
                return StreamMode.BUFFERED

        if policy.stream is StreamCapability.INCREMENTAL:
            return StreamMode.INCREMENTAL
        return StreamMode.BUFFERED

    async def preview(
        self,
        content: Any,
        principal: Principal,
        stage: WorkflowStage,
        policy: ResolvedPolicy,
    ) -> PolicyDecision:
        """Run an explicit ``policy`` against ``content`` without resolving it.

        Lets an operator test a policy they have not saved yet, through the
        same adapters, composition and mode handling that enforcement uses. A
        preview built on a parallel code path would verify the preview rather
        than the policy: it could not show one adapter's BLOCK overriding
        another's TRANSFORM, nor a monitor-mode verdict that applies nothing,
        nor an adapter named but not registered — which fails closed and is
        exactly the mistake worth catching before saving rather than after.

        Deliberately not audited. A preview is a hypothetical, and recording it
        would put events into the compliance trail that never happened to real
        traffic.
        """
        specs = policy.adapters_for(stage)
        context = EvaluationContext(
            workflow_stage=stage,
            principal=principal,
            run_id=get_run_id(),
            policy_version=policy.version,
        )
        if not specs:
            return PolicyDecision(policy_version=policy.version)

        return await self._assess(content, policy, specs, context)

    async def _assess(
        self,
        content: Any,
        policy: ResolvedPolicy,
        specs: Sequence[AdapterSpec],
        context: EvaluationContext,
    ) -> PolicyDecision:
        """Run the configured adapters over ``content`` and compose a verdict.

        The bare assessment, with none of the bookkeeping. What the three
        public entry points differ in is precisely that bookkeeping — whether
        the verdict is cached, logged and audited — so keeping it out of here
        makes those differences the only thing that has to be read to tell
        them apart.
        """
        results = await self._run_adapters(content, context, specs)
        return await self._decide(content, results, policy, context, specs)

    async def evaluate_prefix(
        self,
        content: Any,
        principal: Principal,
        stage: WorkflowStage,
        destination: Optional[str] = None,
    ) -> PolicyDecision:
        """Advisory verdict on part of a response. Never audited, never cached.

        Used by a guarded stream to decide how much of what it has so far may
        be released. Only ``evaluate`` writes to the compliance trail, and it
        is called once per response, on the whole response.

        Not audited, because a prefix scan is not an event. Fifteen scans of a
        growing response are one finding observed fifteen times, and fifteen
        audit rows would report entity counts climbing as the model types --
        which is not a record of what happened, it is a record of how it was
        measured. Any "how many responses did PII block this week" query would
        then be off by however many chunks the provider happened to emit.

        Not cached either, in either direction. Every prefix is a distinct
        cache key (see ``_cache_key``), so a stored prefix verdict can never be
        read again: it is a write-once entry that evicts entries which *are*
        re-read -- a conversation's history verdicts -- from a budget of
        VERDICT_CACHE_CHAR_BUDGET characters charged at _ENTRY_OVERHEAD_CHARS
        apiece. One streamed response would churn a measurable fraction of the
        cache the policy actually depends on, to store entries that are certain
        to be dead.

        A separate method rather than ``evaluate(audit=False, cache=False)``:
        a bypass parameter on the main entry point is reachable by accident,
        and the accident is silent -- a future call site passing it drops
        compliance rows nobody notices are missing. A narrowly named method
        whose docstring says "advisory" is greppable and hard to misuse.
        """
        policy = await self._resolve(principal)
        specs = policy.adapters_for(stage)
        if not specs:
            return PolicyDecision(policy_version=policy.version)

        context = EvaluationContext(
            workflow_stage=stage,
            principal=principal,
            run_id=get_run_id(),
            destination=destination,
            policy_version=policy.version,
        )
        decision = await self._assess(content, policy, specs, context)

        # DEBUG, not INFO: one line per scan would drown the single line that
        # describes the response actually delivered.
        logger.debug(
            f'Guardrail {stage.value} prefix -> {decision.observed_action.value} '
            f'[ns={principal.namespace or "-"} '
            f'agent={principal.agent_id or "-"}] {len(content)} chars'
        )
        return decision

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
            # The most common "why isn't it working?" case, so say which of the
            # two reasons applies rather than staying silent.
            reason = (
                'policy disabled'
                if not policy.is_enabled
                else f'no adapters configured for {stage.value}'
            )
            logger.debug(
                f'Guardrail {stage.value} skipped ({reason}) '
                f'[ns={principal.namespace or "-"} agent={principal.agent_id or "-"}]'
            )
            return PolicyDecision(policy_version=policy.version)

        # A verdict already derived for this content under this policy is
        # returned as it stands. It is deliberately not logged or audited a
        # second time: the finding is the same finding, and one row per
        # re-send would bury the trail rather than enrich it.
        key = self._cache_key(content, principal, stage, policy)
        if key is not None:
            cached = await self._verdicts.get(key)
            if cached is not None:
                logger.debug(
                    f'Guardrail {stage.value} verdict reused '
                    f'[ns={principal.namespace or "-"} '
                    f'agent={principal.agent_id or "-"}]'
                )
                return cached

        decision = await self._assess(content, policy, specs, context)
        self._log_decision(decision, context, specs)
        await self._audit(decision, context)

        # An error verdict describes the provider, not the content. Fail-open
        # turned an outage into ALLOW and fail-closed turned it into BLOCK;
        # keeping either would outlive the outage that justified it - the
        # first as a bypass, the second as an outage that never ends.
        if key is not None and not any(r.is_error for r in decision.results):
            await self._verdicts.store(key, decision)
        return decision

    def _cache_key(
        self,
        content: Any,
        principal: Principal,
        stage: WorkflowStage,
        policy: ResolvedPolicy,
    ) -> Optional[str]:
        """Identity of "this content, judged by this policy", or ``None`` when
        the payload cannot be cached.

        The namespace is in the key because policy is resolved per namespace:
        two tenants can run different adapters over identical text and must
        not share a verdict. The stage is in it because a policy can configure
        different adapters before and after the model. The version is, so that
        editing a policy retires every verdict it produced.

        All four are folded into the digest rather than only concatenated into
        the prefix, so a namespace containing the separator cannot be made to
        collide with another one. The readable prefix is kept anyway: it is
        what makes a shared cache greppable, and lets an operator scan or drop
        one namespace's entries without being able to read any of them.

        The digest is keyed when a secret is configured. Plain SHA-256 of a
        short payload is not a privacy barrier — see the warning in __init__.
        """
        if not isinstance(content, str):
            return None

        namespace = principal.namespace or ''
        identity = '\x00'.join(
            (namespace, stage.value, policy.version or '', content)
        ).encode('utf-8')

        if self._key_secret is not None:
            digest = hmac.new(self._key_secret, identity, hashlib.sha256).hexdigest()
        else:
            digest = hashlib.sha256(identity).hexdigest()

        return f'{namespace}:{stage.value}:{digest}'

    def _log_decision(
        self,
        decision: PolicyDecision,
        context: EvaluationContext,
        specs: Sequence[AdapterSpec],
    ) -> None:
        """Emit one line per evaluation so enforcement is verifiable from logs.

        Findings are summarised as codes, entity types and counts. The
        evaluated content and the matched values never appear: a guardrail that
        logs the PII it just found has only moved the leak somewhere else.

        A clean result is DEBUG because it happens on every call. Anything the
        policy reacted to is INFO, because it is rare and is the record of the
        control having done something.
        """
        stage = context.workflow_stage.value
        where = (
            f'ns={context.namespace or "-"} agent={context.agent_id or "-"} '
            f'run={context.run_id or "-"}'
        )

        if decision.observed_action is PolicyAction.ALLOW and not any(
            r.is_error for r in decision.results
        ):
            logger.debug(
                f'Guardrail {stage} clean '
                f'[{where} adapters={", ".join(s.name for s in specs)}]'
            )
            return

        details = []
        for result in decision.results:
            if result.action is PolicyAction.ALLOW and not result.is_error:
                continue
            bits = [f'{result.adapter}={result.action.value}']
            if result.finding_code:
                bits.append(result.finding_code)
            counts = result.provider_metadata.get('entity_counts')
            if counts:
                bits.append(str(counts))
            if result.severity is not None:
                bits.append(f'severity={result.severity:.2f}')
            if result.is_error:
                bits.append(f'error={result.failure_class.value}')
                if result.message:
                    bits.append(f'({result.message})')
            details.append(' '.join(bits))

        logger.info(
            f'Guardrail {stage} -> {decision.observed_action.value} '
            f'({"ENFORCED" if decision.enforced else "MONITOR"}) '
            f'[{where}] {"; ".join(details)}'
        )

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
            # _log_decision reports it, tagged MONITOR.
            action = PolicyAction.ALLOW

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
