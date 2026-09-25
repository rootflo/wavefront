"""The engine's verdict cache: what may be reused, and what may not.

The cache exists because one message is evaluated many times — a
conversation re-sends its history every turn, a tool loop re-sends the turn
every iteration, and a workflow runs many nodes against one namespace's
policy — and a safety provider bills per call.

Kept separate from test_guardrails_engine.py, which covers policy resolution
and adapter orchestration.
"""

from flo_ai.guardrails import (
    AdapterSpec,
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
AFTER = WorkflowStage.AFTER_MODEL
ACME = Principal(namespace='acme')


class CountingAdapter(BaseAdapter):
    """Records every payload it is asked about, so calls can be counted."""

    def __init__(self, name='counting', behaviour='allow'):
        self._name = name
        self.behaviour = behaviour
        self.seen = []

    @property
    def name(self):
        return self._name

    async def evaluate(self, request):
        self.seen.append(request.content)
        if self.behaviour == 'transform':
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.TRANSFORM,
                adapter=self._name,
                transformed_content='<redacted>',
                message='redacted',
            )
        if self.behaviour == 'infra_error':
            return CheckResult(
                status=AssessmentStatus.ERROR,
                action=PolicyAction.BLOCK,
                adapter=self._name,
                failure_class=FailureClass.INFRASTRUCTURE,
                message='provider down',
            )
        return self._allow()


class MutableResolver:
    """Resolver whose policy can be swapped, standing in for an edited row."""

    def __init__(self, policy):
        self.policy = policy

    async def resolve(self, principal):
        return self.policy


class RecordingAudit:
    def __init__(self):
        self.records = []

    async def record(self, decision, context):
        self.records.append((decision, context))


def policy_for(adapter, stages=(BEFORE,), version='v1', on_error=FailureMode.FAIL_OPEN):
    return ResolvedPolicy(
        is_enabled=True,
        mode=EnforcementMode.ENFORCE,
        adapters=(
            AdapterSpec(name=adapter.name, stages=tuple(stages), on_error=on_error),
        ),
        version=version,
    )


def build(adapter, resolver=None, **kwargs):
    return GuardrailsEngine(
        resolver=resolver or StaticPolicyResolver(policy_for(adapter)),
        adapters=[adapter],
        **kwargs,
    )


class TestReuse:
    async def test_the_same_content_is_evaluated_once(self):
        adapter = CountingAdapter()
        engine = build(adapter)

        for _ in range(3):
            await engine.evaluate('hello', ACME, BEFORE)

        assert adapter.seen == ['hello'], 'a provider must not be billed per re-send'

    async def test_a_reused_verdict_carries_the_same_transform(self):
        adapter = CountingAdapter(behaviour='transform')
        engine = build(adapter)

        first = await engine.evaluate('secret', ACME, BEFORE)
        second = await engine.evaluate('secret', ACME, BEFORE)

        assert second.action is PolicyAction.TRANSFORM
        assert second.transformed_content == first.transformed_content == '<redacted>'

    async def test_the_cache_can_be_turned_off(self):
        adapter = CountingAdapter()
        engine = build(adapter, verdict_cache_chars=0)

        await engine.evaluate('hello', ACME, BEFORE)
        await engine.evaluate('hello', ACME, BEFORE)

        assert adapter.seen == ['hello', 'hello']

    async def test_a_reused_verdict_is_not_audited_twice(self):
        """One finding, one row. A row per re-send buries the trail.

        The first occurrence is what the compliance record needs; the tenth
        time the same history is re-sent is not a new event.
        """
        audit = RecordingAudit()
        adapter = CountingAdapter(behaviour='transform')
        engine = build(adapter, audit_sink=audit)

        await engine.evaluate('secret', ACME, BEFORE)
        await engine.evaluate('secret', ACME, BEFORE)

        assert len(audit.records) == 1


class TestWhatMustNotBeReused:
    async def test_an_error_verdict_is_not_cached(self):
        """The case that would turn a cache into a standing bypass.

        Fail-open answers ALLOW while a provider is unreachable. That verdict
        describes the outage, not the content, so caching it would keep
        letting the same payload through long after the provider recovered.
        """
        adapter = CountingAdapter(behaviour='infra_error')
        engine = build(adapter)

        during = await engine.evaluate('secret', ACME, BEFORE)
        assert during.action is PolicyAction.ALLOW, 'fail-open during the outage'

        adapter.behaviour = 'transform'  # provider recovers
        after = await engine.evaluate('secret', ACME, BEFORE)

        assert adapter.seen == ['secret', 'secret'], 'outage verdict must not stand'
        assert after.action is PolicyAction.TRANSFORM

    async def test_a_fail_closed_error_is_not_cached_either(self):
        """The mirror image: an outage that would never end.

        Fail-closed answers BLOCK, and caching that would keep rejecting the
        payload after the provider came back.
        """
        adapter = CountingAdapter(behaviour='infra_error')
        engine = build(
            adapter,
            resolver=StaticPolicyResolver(
                policy_for(adapter, on_error=FailureMode.FAIL_CLOSED)
            ),
        )

        during = await engine.evaluate('anything', ACME, BEFORE)
        assert during.blocked

        adapter.behaviour = 'allow'  # provider recovers
        after = await engine.evaluate('anything', ACME, BEFORE)

        assert after.action is PolicyAction.ALLOW

    async def test_two_namespaces_do_not_share_a_verdict(self):
        """Policy is resolved per namespace, so the same text can be judged
        by different adapters with different options.
        """
        adapter = CountingAdapter()
        engine = build(adapter)

        await engine.evaluate('hello', Principal(namespace='acme'), BEFORE)
        await engine.evaluate('hello', Principal(namespace='other'), BEFORE)

        assert adapter.seen == ['hello', 'hello']

    async def test_the_two_stages_do_not_share_a_verdict(self):
        """A policy can configure different adapters before and after the
        model, so a verdict at one stage says nothing about the other.
        """
        adapter = CountingAdapter()
        engine = build(
            adapter,
            resolver=StaticPolicyResolver(policy_for(adapter, stages=(BEFORE, AFTER))),
        )

        await engine.evaluate('hello', ACME, BEFORE)
        await engine.evaluate('hello', ACME, AFTER)

        assert adapter.seen == ['hello', 'hello']

    async def test_editing_the_policy_retires_the_cache(self):
        adapter = CountingAdapter()
        resolver = MutableResolver(policy_for(adapter, version='v1'))
        engine = build(adapter, resolver=resolver)

        await engine.evaluate('secret', ACME, BEFORE)

        adapter.behaviour = 'transform'
        resolver.policy = policy_for(adapter, version='v2')
        after = await engine.evaluate('secret', ACME, BEFORE)

        assert adapter.seen == ['secret', 'secret']
        assert after.action is PolicyAction.TRANSFORM

    async def test_content_that_is_not_text_is_not_cached(self):
        """The key is a digest of text, so anything else is evaluated afresh
        rather than silently sharing one entry.
        """
        adapter = CountingAdapter()
        engine = build(adapter)
        payload = {'not': 'text'}

        await engine.evaluate(payload, ACME, BEFORE)
        await engine.evaluate(payload, ACME, BEFORE)

        assert len(adapter.seen) == 2

    async def test_a_preview_is_never_served_from_the_cache(self):
        """An operator testing a policy must see what it does now."""
        adapter = CountingAdapter()
        engine = build(adapter)
        draft = policy_for(adapter)

        await engine.preview('hello', ACME, BEFORE, draft)
        await engine.preview('hello', ACME, BEFORE, draft)

        assert adapter.seen == ['hello', 'hello']
