import asyncio

import pytest

from flo_ai.guardrails import (
    AdapterSpec,
    AssessmentRequest,
    AssessmentStatus,
    CheckResult,
    EnforcementMode,
    FailureClass,
    FailureMode,
    GuardrailsEngine,
    PolicyAction,
    Principal,
    ResolvedPolicy,
    StaticPolicyResolver,
    WorkflowStage,
)
from flo_ai.guardrails.adapters.base_adapter import BaseAdapter

BEFORE = WorkflowStage.BEFORE_MODEL


class FakeAdapter(BaseAdapter):
    """Adapter with scripted behaviour, recording every call it receives."""

    def __init__(self, name='fake', behaviour='allow', transform_to=None, delay=0.0):
        self._name = name
        self.behaviour = behaviour
        self.transform_to = transform_to
        self.delay = delay
        self.calls = []
        self.closed = False

    @property
    def name(self):
        return self._name

    async def aclose(self):
        self.closed = True

    async def evaluate(self, request: AssessmentRequest) -> CheckResult:
        self.calls.append(request.content)
        if self.delay:
            await asyncio.sleep(self.delay)

        if self.behaviour == 'allow':
            return self._allow()
        if self.behaviour == 'block':
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.BLOCK,
                adapter=self._name,
                message=f'{self._name} says no',
            )
        if self.behaviour == 'transform':
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.TRANSFORM,
                adapter=self._name,
                transformed_content=self.transform_to,
                message=f'{self._name} redacted',
            )
        if self.behaviour == 'infra_error':
            return self._error(FailureClass.INFRASTRUCTURE, 'provider down')
        if self.behaviour == 'input_rejected':
            return self._error(FailureClass.INPUT_REJECTED, 'content too large')
        if self.behaviour == 'raise':
            raise RuntimeError('adapter exploded')
        raise AssertionError(f'unknown behaviour {self.behaviour}')


class RecordingAudit:
    def __init__(self):
        self.records = []

    async def record(self, decision, context):
        self.records.append((decision, context))


def policy(*specs, enabled=True, mode=EnforcementMode.ENFORCE, version='v1'):
    return ResolvedPolicy(
        is_enabled=enabled, mode=mode, adapters=tuple(specs), version=version
    )


def spec(name='fake', stages=(BEFORE,), on_error=FailureMode.FAIL_OPEN, timeout=5.0):
    return AdapterSpec(
        name=name, stages=tuple(stages), on_error=on_error, timeout_seconds=timeout
    )


def build(policy_obj, *adapters, audit=None):
    return GuardrailsEngine(
        resolver=StaticPolicyResolver(policy_obj), adapters=adapters, audit_sink=audit
    )


class TestMasterSwitch:
    async def test_disabled_policy_runs_no_adapters(self):
        adapter = FakeAdapter(behaviour='block')
        engine = build(policy(spec(), enabled=False), adapter)

        decision = await engine.evaluate('anything', Principal(), BEFORE)

        assert decision.action is PolicyAction.ALLOW
        assert adapter.calls == [], 'disabled policy must not call providers'

    async def test_engine_without_resolver_is_inert(self):
        adapter = FakeAdapter(behaviour='block')
        engine = GuardrailsEngine(adapters=[adapter])

        decision = await engine.evaluate('anything', Principal(), BEFORE)

        assert decision.action is PolicyAction.ALLOW
        assert adapter.calls == []

    async def test_adapter_not_configured_for_stage_is_skipped(self):
        adapter = FakeAdapter(behaviour='block')
        engine = build(policy(spec(stages=(WorkflowStage.AFTER_MODEL,))), adapter)

        decision = await engine.evaluate('hi', Principal(), BEFORE)

        assert decision.action is PolicyAction.ALLOW
        assert adapter.calls == []


class TestVerdicts:
    async def test_block(self):
        engine = build(policy(spec()), FakeAdapter(behaviour='block'))

        decision = await engine.evaluate('bad', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK
        assert decision.blocked
        assert decision.block_reasons() == ['fake says no']

    async def test_single_transform(self):
        adapter = FakeAdapter(behaviour='transform', transform_to='<redacted>')
        engine = build(policy(spec()), adapter)

        decision = await engine.evaluate('my ssn', Principal(), BEFORE)

        assert decision.action is PolicyAction.TRANSFORM
        assert decision.transformed_content == '<redacted>'

    async def test_block_wins_over_transform(self):
        engine = build(
            policy(spec(name='a'), spec(name='b')),
            FakeAdapter(name='a', behaviour='transform', transform_to='x'),
            FakeAdapter(name='b', behaviour='block'),
        )

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK

    async def test_multiple_transforms_are_chained_not_overwritten(self):
        """Each rewriter must see its predecessor's output.

        Running them concurrently on the original and keeping the last result
        silently discards the other's redaction.
        """
        first = FakeAdapter(name='a', behaviour='transform', transform_to='A')
        second = FakeAdapter(name='b', behaviour='transform', transform_to='B')
        engine = build(policy(spec(name='a'), spec(name='b')), first, second)

        decision = await engine.evaluate('original', Principal(), BEFORE)

        assert decision.action is PolicyAction.TRANSFORM
        # 'b' was re-run against 'a' output rather than the original.
        assert second.calls[-1] == 'A'
        assert decision.transformed_content == 'B'


class TestMonitorMode:
    async def test_monitor_records_but_does_not_enforce(self):
        engine = build(
            policy(spec(), mode=EnforcementMode.MONITOR),
            FakeAdapter(behaviour='block'),
        )

        decision = await engine.evaluate('bad', Principal(), BEFORE)

        assert decision.action is PolicyAction.ALLOW
        assert decision.observed_action is PolicyAction.BLOCK
        assert decision.enforced is False
        assert decision.blocked is False

    async def test_monitor_does_not_apply_transforms(self):
        engine = build(
            policy(spec(), mode=EnforcementMode.MONITOR),
            FakeAdapter(behaviour='transform', transform_to='<redacted>'),
        )

        decision = await engine.evaluate('pii', Principal(), BEFORE)

        assert decision.transformed_content is None
        assert decision.transformed is False
        assert decision.observed_action is PolicyAction.TRANSFORM


class TestFailureClassification:
    async def test_infrastructure_error_fails_open_when_policy_allows(self):
        engine = build(
            policy(spec(on_error=FailureMode.FAIL_OPEN)),
            FakeAdapter(behaviour='infra_error'),
        )

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.ALLOW

    async def test_infrastructure_error_fails_closed_when_policy_says_so(self):
        engine = build(
            policy(spec(on_error=FailureMode.FAIL_CLOSED)),
            FakeAdapter(behaviour='infra_error'),
        )

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK

    async def test_input_rejection_ignores_fail_open(self):
        """Oversized/wrong-typed content is caller-controlled.

        Honouring fail-open here would let anyone bypass the guardrail on
        demand by padding their prompt past the provider's limit.
        """
        engine = build(
            policy(spec(on_error=FailureMode.FAIL_OPEN)),
            FakeAdapter(behaviour='input_rejected'),
        )

        decision = await engine.evaluate('x' * 99, Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK

    async def test_unregistered_adapter_ignores_fail_open(self):
        engine = build(
            policy(spec(name='not_registered', on_error=FailureMode.FAIL_OPEN))
        )

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK
        assert decision.results[0].failure_class is FailureClass.MISCONFIGURED

    async def test_unhandled_exception_is_infrastructure(self):
        engine = build(
            policy(spec(on_error=FailureMode.FAIL_CLOSED)),
            FakeAdapter(behaviour='raise'),
        )

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK
        assert decision.results[0].failure_class is FailureClass.INFRASTRUCTURE

    async def test_timeout_is_infrastructure(self):
        engine = build(
            policy(spec(on_error=FailureMode.FAIL_CLOSED, timeout=0.01)),
            FakeAdapter(behaviour='allow', delay=0.5),
        )

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK
        assert decision.results[0].finding_code == 'guardrail.timeout'

    async def test_phase_two_stages_are_rejected_not_silently_skipped(self):
        engine = build(
            policy(spec(stages=(WorkflowStage.BEFORE_TOOL,))),
            FakeAdapter(behaviour='allow'),
        )

        decision = await engine.evaluate('args', Principal(), WorkflowStage.BEFORE_TOOL)

        assert decision.action is PolicyAction.BLOCK
        assert decision.results[0].failure_class is FailureClass.MISCONFIGURED

    async def test_resolver_failure_does_not_enforce_but_is_not_silent(self, caplog):
        class BrokenResolver:
            async def resolve(self, principal):
                raise RuntimeError('database is down')

        engine = GuardrailsEngine(resolver=BrokenResolver())

        decision = await engine.evaluate('text', Principal(), BEFORE)

        assert decision.action is PolicyAction.ALLOW


class TestAudit:
    async def test_block_is_recorded(self):
        audit = RecordingAudit()
        engine = build(policy(spec()), FakeAdapter(behaviour='block'), audit=audit)

        await engine.evaluate('bad', Principal(namespace='acme'), BEFORE)

        assert len(audit.records) == 1
        decision, context = audit.records[0]
        assert decision.observed_action is PolicyAction.BLOCK
        assert context.namespace == 'acme'

    async def test_clean_allow_is_not_recorded(self):
        audit = RecordingAudit()
        engine = build(policy(spec()), FakeAdapter(behaviour='allow'), audit=audit)

        await engine.evaluate('fine', Principal(), BEFORE)

        assert audit.records == []

    async def test_monitor_mode_still_records(self):
        audit = RecordingAudit()
        engine = build(
            policy(spec(), mode=EnforcementMode.MONITOR),
            FakeAdapter(behaviour='block'),
            audit=audit,
        )

        await engine.evaluate('bad', Principal(), BEFORE)

        assert len(audit.records) == 1, 'monitor mode exists to collect this data'

    async def test_audit_failure_does_not_break_the_request(self):
        class BrokenAudit:
            async def record(self, decision, context):
                raise RuntimeError('audit store down')

        engine = build(
            policy(spec()), FakeAdapter(behaviour='block'), audit=BrokenAudit()
        )

        decision = await engine.evaluate('bad', Principal(), BEFORE)

        assert decision.action is PolicyAction.BLOCK


class TestLifecycle:
    async def test_has_checks(self):
        engine = build(policy(spec(stages=(BEFORE,))), FakeAdapter())

        assert await engine.has_checks(Principal(), BEFORE) is True
        assert await engine.has_checks(Principal(), WorkflowStage.AFTER_MODEL) is False

    async def test_aclose_closes_every_adapter(self):
        a, b = FakeAdapter(name='a'), FakeAdapter(name='b')
        engine = build(policy(spec()), a, b)

        await engine.aclose()

        assert a.closed and b.closed

    async def test_adapter_registers_under_its_own_name(self):
        engine = build(policy(spec()), FakeAdapter(name='declared'))

        assert engine.registered == ('declared',)


class TestOptionsPassing:
    async def test_policy_options_reach_the_adapter(self):
        seen = {}

        class OptionAdapter(FakeAdapter):
            async def evaluate(self, request):
                seen.update(request.options)
                return self._allow()

        engine = build(
            policy(
                AdapterSpec(
                    name='fake', stages=(BEFORE,), options={'severity_threshold': 6}
                )
            ),
            OptionAdapter(),
        )

        await engine.evaluate('text', Principal(), BEFORE)

        assert seen == {'severity_threshold': 6}


@pytest.mark.parametrize(
    'stage', [WorkflowStage.BEFORE_MODEL, WorkflowStage.AFTER_MODEL]
)
async def test_context_carries_principal_and_stage(stage):
    captured = {}

    class ContextAdapter(FakeAdapter):
        async def evaluate(self, request):
            captured['stage'] = request.context.workflow_stage
            captured['agent'] = request.context.agent_id
            return self._allow()

    engine = build(policy(spec(stages=(stage,))), ContextAdapter())
    await engine.evaluate('text', Principal(agent_id='agent-7'), stage)

    assert captured == {'stage': stage, 'agent': 'agent-7'}
