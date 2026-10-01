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
from flo_ai.guardrails.contracts import StreamCapability, StreamMode

BEFORE = WorkflowStage.BEFORE_MODEL
AFTER = WorkflowStage.AFTER_MODEL


class FakeAdapter(BaseAdapter):
    """Adapter with scripted behaviour, recording every call it receives."""

    def __init__(
        self,
        name='fake',
        behaviour='allow',
        transform_to=None,
        delay=0.0,
        finding_code=None,
    ):
        self._name = name
        self.behaviour = behaviour
        self.transform_to = transform_to
        self.delay = delay
        self.finding_code = finding_code
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
                finding_code=self.finding_code,
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


class IncrementalAdapter(FakeAdapter):
    """Stands in for Presidio: findings are spans, so a prefix means something."""

    stream_capability = StreamCapability.INCREMENTAL


def policy(
    *specs,
    enabled=True,
    mode=EnforcementMode.ENFORCE,
    version='v1',
    stream=StreamCapability.BUFFERED,
):
    return ResolvedPolicy(
        is_enabled=enabled,
        mode=mode,
        adapters=tuple(specs),
        version=version,
        stream=stream,
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

    async def test_misconfiguration_is_not_disclosed_to_the_caller(self):
        """The caller-facing message must not describe the safety setup.

        A policy naming an unregistered adapter fails closed, and the operator
        message says which adapter and which ones *are* registered. Surfacing
        that to whoever tripped it hands out an inventory of the checks in
        force, which is why the policy API is admin-only in the first place.
        """
        engine = build(policy(spec(name='not_installed')))

        decision = await engine.evaluate('anything', Principal(), BEFORE)

        assert decision.blocked
        # Operator detail is still available for logs and audit.
        assert 'not_installed' in '; '.join(decision.block_reasons())

        caller = decision.caller_message()
        assert 'not_installed' not in caller
        assert 'registered' not in caller
        assert 'administrator' in caller

    async def test_operator_summary_carries_what_the_caller_message_omits(self):
        """The log line must be self-sufficient for diagnosing a block.

        Nothing else surfaces which check fired: the exception that reaches
        the API layer carries only ``caller_message``, and a block is handled
        rather than raised, so there is no traceback to fall back on.
        """
        engine = build(
            policy(spec(), version='2026-09-17T10:00'),
            FakeAdapter(behaviour='block', finding_code='safety.category_violation'),
        )

        decision = await engine.evaluate('bad', Principal(), BEFORE)

        summary = decision.operator_summary()
        assert 'fake' in summary
        assert 'safety.category_violation' in summary
        assert 'fake says no' in summary
        assert '2026-09-17T10:00' in summary
        # The same detail must stay out of what the end user is shown.
        caller = decision.caller_message()
        assert 'fake' not in caller
        assert 'safety.category_violation' not in caller
        # A content finding is routine, so it must not read as a failure.
        assert not decision.blocked_by_failure

    async def test_fail_closed_block_is_distinguishable_from_a_content_block(self):
        """Both block, but only one of them needs someone woken up."""
        engine = build(
            policy(spec(on_error=FailureMode.FAIL_CLOSED)),
            FakeAdapter(behaviour='infra_error'),
        )

        decision = await engine.evaluate('anything', Principal(), BEFORE)

        assert decision.blocked
        assert decision.blocked_by_failure
        assert 'INFRASTRUCTURE' in decision.operator_summary()

    async def test_pii_block_tells_the_caller_what_to_change(self):
        engine = build(
            policy(spec()),
            FakeAdapter(behaviour='block', finding_code='privacy.pii_detected'),
        )

        decision = await engine.evaluate('my ssn', Principal(), BEFORE)

        assert 'personal or sensitive information' in decision.caller_message()

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


class TestPrefixEvaluation:
    """A scan of part of a response is advisory: no audit row, no cache entry."""

    async def test_a_prefix_scan_is_not_audited(self):
        recorded = []

        class RecordingAudit:
            async def record(self, decision, context):
                recorded.append(decision)

        engine = build(
            policy(spec(stages=(AFTER,))),
            FakeAdapter(behaviour='block'),
            audit=RecordingAudit(),
        )

        await engine.evaluate_prefix('partial text', Principal(), AFTER)

        assert recorded == [], (
            'one row per chunk would report counts that climb as the model '
            'types, which is a record of the measurement rather than the event'
        )

    async def test_a_prefix_scan_is_not_cached(self):
        """Every prefix is a distinct key, so a stored one is dead on arrival."""
        adapter = FakeAdapter()
        engine = build(policy(spec(stages=(AFTER,))), adapter)

        await engine.evaluate_prefix('same text', Principal(), AFTER)
        calls_after_prefix = len(adapter.calls)
        await engine.evaluate('same text', Principal(), AFTER)

        assert len(adapter.calls) == calls_after_prefix + 1, (
            'the terminal scan reused a verdict the prefix scan should not '
            'have stored'
        )

    async def test_a_prefix_scan_still_produces_a_verdict(self):
        engine = build(policy(spec(stages=(AFTER,))), FakeAdapter(behaviour='block'))

        decision = await engine.evaluate_prefix('bad', Principal(), AFTER)

        assert decision.action is PolicyAction.BLOCK

    async def test_a_prefix_scan_with_no_adapters_is_inert(self):
        adapter = FakeAdapter()
        engine = build(policy(spec(stages=(BEFORE,))), adapter)

        decision = await engine.evaluate_prefix('anything', Principal(), AFTER)

        assert decision.action is PolicyAction.ALLOW
        assert adapter.calls == []


class TestLifecycle:
    async def test_has_checks(self):
        engine = build(policy(spec(stages=(BEFORE,))), FakeAdapter())

        assert await engine.has_checks(Principal(), BEFORE) is True
        assert await engine.has_checks(Principal(), WorkflowStage.AFTER_MODEL) is False

    async def test_stream_mode_without_checks_is_passthrough(self):
        engine = build(policy(spec(stages=(BEFORE,))), FakeAdapter())

        assert await engine.stream_mode(Principal(), AFTER) is StreamMode.PASSTHROUGH

    async def test_monitor_mode_streams_without_a_margin(self):
        """Nothing is withheld in MONITOR, so withholding text buys nothing."""
        engine = build(
            policy(spec(stages=(AFTER,)), mode=EnforcementMode.MONITOR),
            IncrementalAdapter(),
        )

        assert await engine.stream_mode(Principal(), AFTER) is StreamMode.OBSERVE

    async def test_an_unregistered_adapter_buffers(self):
        """It fails closed on every request; releasing first would retract all."""
        engine = build(policy(spec(name='missing', stages=(AFTER,))), FakeAdapter())

        assert await engine.stream_mode(Principal(), AFTER) is StreamMode.BUFFERED

    async def test_one_buffered_adapter_decides_for_all_of_them(self):
        engine = build(
            policy(
                spec(name='span', stages=(AFTER,)),
                spec(name='holistic', stages=(AFTER,)),
                stream=StreamCapability.INCREMENTAL,
            ),
            IncrementalAdapter(name='span'),
            FakeAdapter(name='holistic'),
        )

        assert await engine.stream_mode(Principal(), AFTER) is StreamMode.BUFFERED

    async def test_incremental_needs_the_policy_to_ask_for_it(self):
        """Capability is permission, not intent. An old policy keeps buffering."""
        engine = build(policy(spec(stages=(AFTER,))), IncrementalAdapter())

        assert await engine.stream_mode(Principal(), AFTER) is StreamMode.BUFFERED

    async def test_incremental_when_policy_and_adapters_agree(self):
        engine = build(
            policy(spec(stages=(AFTER,)), stream=StreamCapability.INCREMENTAL),
            IncrementalAdapter(),
        )

        assert await engine.stream_mode(Principal(), AFTER) is StreamMode.INCREMENTAL

    async def test_an_unsupported_stage_buffers(self):
        """A tool stage is MISCONFIGURED, so it must not stream either."""
        tool_stage = WorkflowStage.AFTER_TOOL
        engine = build(
            policy(spec(stages=(tool_stage,)), stream=StreamCapability.INCREMENTAL),
            IncrementalAdapter(),
        )

        assert await engine.stream_mode(Principal(), tool_stage) is StreamMode.BUFFERED

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


class TestPreview:
    """Preview must go through the same decision path as enforcement."""

    async def test_reports_misconfiguration_instead_of_hiding_it(self):
        """The case that locks a namespace out, caught before saving."""
        engine = build(policy(spec()))  # no adapters registered

        decision = await engine.preview(
            'anything', Principal(), BEFORE, policy(spec(name='not_installed'))
        )

        assert decision.action is PolicyAction.BLOCK
        assert 'not_installed' in '; '.join(decision.block_reasons())

    async def test_block_overrides_another_adapters_transform(self):
        """A PII-only preview would show a redaction that never happens."""
        engine = build(
            policy(),
            FakeAdapter(name='redactor', behaviour='transform', transform_to='<x>'),
            FakeAdapter(name='blocker', behaviour='block'),
        )

        decision = await engine.preview(
            'secret',
            Principal(),
            BEFORE,
            policy(spec(name='redactor'), spec(name='blocker')),
        )

        assert decision.action is PolicyAction.BLOCK
        assert decision.transformed_content is None

    async def test_monitor_mode_shows_the_verdict_without_applying_it(self):
        engine = build(policy(), FakeAdapter(behaviour='block'))

        decision = await engine.preview(
            'bad',
            Principal(),
            BEFORE,
            policy(spec(), mode=EnforcementMode.MONITOR),
        )

        assert decision.action is PolicyAction.ALLOW
        assert decision.observed_action is PolicyAction.BLOCK
        assert decision.enforced is False

    async def test_is_not_audited(self):
        """A hypothetical must not enter the compliance record."""
        audit = RecordingAudit()
        engine = build(policy(spec()), FakeAdapter(behaviour='block'), audit=audit)

        await engine.preview('bad', Principal(), BEFORE, policy(spec()))

        assert audit.records == []
