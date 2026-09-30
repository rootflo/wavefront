"""The shared tier of the verdict cache: what may leave the process.

The in-process cache may hold anything the engine derived. A shared cache is a
different security domain — operators read it, it is snapshotted to disk, and
its credentials are spread across every service that talks to it — so the rule
it has to enforce is that no message body reaches it.

Kept separate from test_guardrails_verdict_cache.py, which covers what may be
reused at all, and from test_guardrails_engine.py, which covers policy
resolution and adapter orchestration.
"""

import pytest

from flo_ai.guardrails import (
    AdapterSpec,
    AssessmentStatus,
    CheckResult,
    EnforcementMode,
    FailureClass,
    GuardrailsEngine,
    LocalVerdictCache,
    PolicyAction,
    PolicyDecision,
    Principal,
    ResolvedPolicy,
    StaticPolicyResolver,
    TieredVerdictCache,
    WorkflowStage,
    carries_content,
    decode_decision,
    encode_decision,
)
from flo_ai.guardrails.adapters.base_adapter import BaseAdapter

BEFORE = WorkflowStage.BEFORE_MODEL
AFTER = WorkflowStage.AFTER_MODEL
ACME = Principal(namespace='acme')

SECRET = 'a-deployment-secret'


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
                finding_code='privacy.pii_detected',
                transformed_content='my number is <PHONE_NUMBER>',
                message='Redacted 1 PII entities: PHONE_NUMBER',
                severity=0.85,
                provider_metadata={'entity_counts': {'PHONE_NUMBER': 1}},
            )
        if self.behaviour == 'block':
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.BLOCK,
                adapter=self._name,
                finding_code='content.hate',
                message='blocked',
                severity=0.9,
            )
        return self._allow()


class FakeSharedCache:
    """A shared backend that enforces the same rule Redis would.

    Stores the *serialised* payload rather than the object, so a test cannot
    pass by handing back a decision the real backend could never have written.
    """

    def __init__(self):
        self.entries = {}
        self.reads = 0
        self.writes = 0

    async def get(self, key):
        self.reads += 1
        raw = self.entries.get(key)
        return decode_decision(raw) if raw is not None else None

    async def store(self, key, decision):
        payload = encode_decision(decision)
        if payload is None:
            return
        self.writes += 1
        self.entries[key] = payload


class ExplodingSharedCache:
    """A backend that is down. Must never surface as a failed request."""

    async def get(self, key):
        raise ConnectionError('redis is down')

    async def store(self, key, decision):
        raise ConnectionError('redis is down')


def policy_for(adapter, stages=(BEFORE,), version='v1'):
    return ResolvedPolicy(
        is_enabled=True,
        mode=EnforcementMode.ENFORCE,
        adapters=(AdapterSpec(name=adapter.name, stages=tuple(stages)),),
        version=version,
    )


def build(adapter, shared=None, secret=SECRET, chars=1_000_000):
    """An engine with its own local tier, optionally behind a shared one.

    Each call is a stand-in for a separate process: distinct adapters and a
    distinct local cache, with only the shared tier held in common.
    """
    cache = None
    if shared is not None:
        cache = TieredVerdictCache(LocalVerdictCache(chars), shared)
    return GuardrailsEngine(
        resolver=StaticPolicyResolver(policy_for(adapter)),
        adapters=[adapter],
        verdict_cache_chars=chars,
        verdict_cache=cache,
        cache_key_secret=secret,
    )


class TestWhatMayBeSerialised:
    """encode_decision is the single gate on what reaches a shared cache."""

    def test_a_transform_is_refused(self):
        """The case the whole design exists for.

        The rewritten text is the evaluated message minus whatever the adapter
        detected — not a message with no PII in it. Presidio removes the entity
        types the policy selected, above its score threshold; anything
        unselected, sub-threshold or unrecognised survives verbatim.
        """
        decision = PolicyDecision(
            action=PolicyAction.TRANSFORM,
            observed_action=PolicyAction.TRANSFORM,
            transformed_content='my number is <PHONE_NUMBER>',
        )

        assert carries_content(decision)
        assert encode_decision(decision) is None

    def test_content_hiding_in_a_result_is_refused_too(self):
        """A decision can be clean at the top level and still carry a body.

        Monitor mode is exactly that shape: the decision's transformed_content
        is dropped because nothing is applied, while the adapter's own result
        still holds what it would have written.
        """
        decision = PolicyDecision(
            action=PolicyAction.ALLOW,
            enforced=False,
            observed_action=PolicyAction.TRANSFORM,
            transformed_content=None,
            results=[
                CheckResult(
                    status=AssessmentStatus.VIOLATION,
                    action=PolicyAction.TRANSFORM,
                    adapter='presidio_pii',
                    transformed_content='my number is <PHONE_NUMBER>',
                )
            ],
        )

        assert carries_content(decision)
        assert encode_decision(decision) is None

    def test_no_payload_ever_contains_the_evaluated_text(self):
        """The guarantee stated as the property a reviewer actually cares about."""
        secret_text = 'call me on 555-123-4567'
        decision = PolicyDecision(
            action=PolicyAction.BLOCK,
            observed_action=PolicyAction.BLOCK,
            results=[
                CheckResult(
                    status=AssessmentStatus.VIOLATION,
                    action=PolicyAction.BLOCK,
                    adapter='azure_content_safety',
                    finding_code='content.hate',
                    message='blocked',
                    provider_metadata={'entity_counts': {'PHONE_NUMBER': 1}},
                )
            ],
        )

        payload = encode_decision(decision)

        assert payload is not None
        assert secret_text not in payload
        assert '555' not in payload

    def test_an_unserialisable_metadata_value_is_refused_not_raised(self):
        """An adapter's metadata must not be able to fail a request.

        The cost of refusing is that this adapter's verdicts stop being
        shared. The cost of raising would be a failed inference call.
        """
        decision = PolicyDecision(
            results=[
                CheckResult(
                    status=AssessmentStatus.PASS,
                    action=PolicyAction.ALLOW,
                    adapter='odd',
                    provider_metadata={'engine': object()},
                )
            ]
        )

        assert encode_decision(decision) is None


class TestRoundTrip:
    def test_a_content_free_verdict_survives_intact(self):
        decision = PolicyDecision(
            action=PolicyAction.BLOCK,
            observed_action=PolicyAction.BLOCK,
            enforced=True,
            policy_version='v7',
            results=[
                CheckResult(
                    status=AssessmentStatus.VIOLATION,
                    action=PolicyAction.BLOCK,
                    adapter='azure_content_safety',
                    finding_code='content.hate',
                    message='severity 4',
                    failure_class=FailureClass.NONE,
                    severity=0.9,
                    provider_metadata={'entity_counts': {'HATE': 1}},
                )
            ],
        )

        restored = decode_decision(encode_decision(decision))

        assert restored.action is PolicyAction.BLOCK
        assert restored.observed_action is PolicyAction.BLOCK
        assert restored.enforced is True
        assert restored.policy_version == 'v7'
        assert restored.blocked
        assert not restored.blocked_by_failure
        assert restored.caller_message() == (
            'This request was blocked by a content safety policy.'
        )
        [result] = restored.results
        assert result.adapter == 'azure_content_safety'
        assert result.finding_code == 'content.hate'
        assert result.severity == 0.9
        assert result.provider_metadata == {'entity_counts': {'HATE': 1}}

    def test_a_monitor_verdict_stays_advisory(self):
        """enforced=False must survive, or a monitored policy starts blocking."""
        decision = PolicyDecision(
            action=PolicyAction.ALLOW,
            observed_action=PolicyAction.BLOCK,
            enforced=False,
            results=[
                CheckResult(
                    status=AssessmentStatus.VIOLATION,
                    action=PolicyAction.BLOCK,
                    adapter='azure_content_safety',
                )
            ],
        )

        restored = decode_decision(encode_decision(decision))

        assert restored.enforced is False
        assert restored.blocked is False
        assert restored.observed_action is PolicyAction.BLOCK

    @pytest.mark.parametrize(
        'raw',
        [
            'not json at all',
            '{"v": 999, "action": "ALLOW", "observed": "ALLOW"}',
            '{"v": 1, "action": "NOT_AN_ACTION", "observed": "ALLOW"}',
            '{"v": 1, "observed": "ALLOW"}',
            '[]',
            '',
        ],
    )
    def test_anything_unreadable_is_a_miss_not_an_error(self, raw):
        """A miss costs one re-evaluation. Guessing costs an invented verdict.

        The schema version matters most during a rolling deploy, when both
        versions are live and writing into one Redis.
        """
        assert decode_decision(raw) is None


class TestTiering:
    async def test_a_local_hit_does_not_touch_the_shared_tier(self):
        shared = FakeSharedCache()
        adapter = CountingAdapter()
        engine = build(adapter, shared)

        await engine.evaluate('hello', ACME, BEFORE)
        reads_after_first = shared.reads
        await engine.evaluate('hello', ACME, BEFORE)

        assert shared.reads == reads_after_first, 'a local hit is a round trip saved'
        assert adapter.seen == ['hello']

    async def test_a_fresh_process_reuses_a_shared_verdict(self):
        """The reason for having a shared tier at all.

        Workers restart, scale out, and run consecutive turns of one
        conversation on different processes. Without this, each one bills the
        provider again for history it has collectively already checked.
        """
        shared = FakeSharedCache()
        first = CountingAdapter()
        await build(first, shared).evaluate('hello', ACME, BEFORE)

        second = CountingAdapter()
        decision = await build(second, shared).evaluate('hello', ACME, BEFORE)

        assert second.seen == [], 'the new process must not re-ask the provider'
        assert decision.action is PolicyAction.ALLOW

    async def test_a_shared_hit_is_promoted_into_the_local_tier(self):
        """One round trip per process, not one per tool-loop iteration."""
        shared = FakeSharedCache()
        await build(CountingAdapter(), shared).evaluate('hello', ACME, BEFORE)

        engine = build(CountingAdapter(), shared)
        await engine.evaluate('hello', ACME, BEFORE)
        reads_after_promotion = shared.reads
        await engine.evaluate('hello', ACME, BEFORE)

        assert shared.reads == reads_after_promotion


class TestTransformsStayLocal:
    async def test_a_redaction_is_reused_in_process(self):
        """Losing this is what made dropping the local tier a regression."""
        adapter = CountingAdapter(behaviour='transform')
        engine = build(adapter, FakeSharedCache())

        first = await engine.evaluate('call me on 555-123-4567', ACME, BEFORE)
        second = await engine.evaluate('call me on 555-123-4567', ACME, BEFORE)

        assert adapter.seen == ['call me on 555-123-4567']
        assert second.transformed_content == first.transformed_content

    async def test_a_redaction_never_reaches_the_shared_tier(self):
        shared = FakeSharedCache()
        engine = build(CountingAdapter(behaviour='transform'), shared)

        await engine.evaluate('call me on 555-123-4567', ACME, BEFORE)

        assert shared.writes == 0
        assert shared.entries == {}

    async def test_a_fresh_process_re_derives_a_redaction(self):
        """The accepted cost of the rule: Presidio runs again, and only Presidio.

        It is local CPU rather than a billed call, which is why this trade is
        the right way round.
        """
        shared = FakeSharedCache()
        await build(CountingAdapter(behaviour='transform'), shared).evaluate(
            'call me on 555-123-4567', ACME, BEFORE
        )

        second = CountingAdapter(behaviour='transform')
        decision = await build(second, shared).evaluate(
            'call me on 555-123-4567', ACME, BEFORE
        )

        assert second.seen == ['call me on 555-123-4567']
        assert decision.transformed_content == 'my number is <PHONE_NUMBER>'

    async def test_a_block_does_reach_the_shared_tier(self):
        """Azure only ever allows or blocks, so its verdicts are shareable.

        That is the whole point: the provider that bills per call is the one
        whose verdicts carry no content.
        """
        shared = FakeSharedCache()
        engine = build(CountingAdapter(behaviour='block'), shared)

        await engine.evaluate('something awful', ACME, BEFORE)

        assert shared.writes == 1


class TestTheSharedTierCannotBreakARequest:
    async def test_a_backend_outage_is_a_miss(self):
        adapter = CountingAdapter()
        engine = build(adapter, ExplodingSharedCache())

        decision = await engine.evaluate('hello', ACME, BEFORE)

        assert decision.action is PolicyAction.ALLOW
        assert adapter.seen == ['hello']

    async def test_the_local_tier_still_works_during_an_outage(self):
        adapter = CountingAdapter()
        engine = build(adapter, ExplodingSharedCache())

        await engine.evaluate('hello', ACME, BEFORE)
        await engine.evaluate('hello', ACME, BEFORE)

        assert adapter.seen == ['hello'], 'the local tier is independent'


class TestCacheKeys:
    def _key(self, engine, content, principal=ACME, stage=BEFORE, version='v1'):
        policy = ResolvedPolicy(is_enabled=True, version=version)
        return engine._cache_key(content, principal, stage, policy)

    def test_a_key_discloses_nothing_but_namespace_and_stage(self):
        """What an operator with Redis access can see."""
        engine = build(CountingAdapter())

        key = self._key(engine, 'call me on 555-123-4567')

        assert key.startswith('acme:BEFORE_MODEL:')
        assert '555' not in key
        assert 'call me' not in key

    def test_the_secret_changes_the_digest(self):
        """The point of keying it: without the secret you cannot rebuild a key.

        A plain digest of short content is brute-forceable — enumerate every
        10-digit number, hash each, match. HMAC makes that require the secret.
        """
        content = '555-123-4567'
        one = self._key(build(CountingAdapter(), secret='secret-one'), content)
        two = self._key(build(CountingAdapter(), secret='secret-two'), content)
        none = self._key(build(CountingAdapter(), secret=None), content)

        assert one != two != none
        assert one != none

    def test_a_separator_in_a_namespace_cannot_forge_another_key(self):
        """Why the identity fields are folded into the digest, not just the prefix.

        Concatenation alone lets ('a:b', stage) and ('a', 'b:' + stage) build
        the same string — a tenant able to name its own namespace could then
        read another tenant's verdicts.
        """
        engine = build(CountingAdapter())

        one = self._key(engine, 'hello', principal=Principal(namespace='a:b'))
        two = self._key(engine, 'hello', principal=Principal(namespace='a'))

        assert one != two

    def test_identity_fields_all_separate_the_key(self):
        engine = build(CountingAdapter())
        base = self._key(engine, 'hello')

        assert self._key(engine, 'hello!') != base
        assert self._key(engine, 'hello', principal=Principal(namespace='x')) != base
        assert self._key(engine, 'hello', stage=AFTER) != base
        assert self._key(engine, 'hello', version='v2') != base

    def test_non_text_content_has_no_key(self):
        engine = build(CountingAdapter())

        assert self._key(engine, {'not': 'text'}) is None


class TestLocalBudget:
    async def test_a_zero_budget_disables_the_local_tier(self):
        adapter = CountingAdapter()
        engine = GuardrailsEngine(
            resolver=StaticPolicyResolver(policy_for(adapter)),
            adapters=[adapter],
            verdict_cache_chars=0,
        )

        await engine.evaluate('hello', ACME, BEFORE)
        await engine.evaluate('hello', ACME, BEFORE)

        assert adapter.seen == ['hello', 'hello']

    async def test_a_zero_budget_still_lets_the_shared_tier_work(self):
        """The knobs are independent: per-process memory and cross-process reuse.

        A memory-constrained worker can keep sharing content-free verdicts
        while holding none of its own.
        """
        shared = FakeSharedCache()
        await build(CountingAdapter(), shared, chars=0).evaluate('hello', ACME, BEFORE)

        second = CountingAdapter()
        await build(second, shared, chars=0).evaluate('hello', ACME, BEFORE)

        assert second.seen == []

    async def test_the_budget_evicts_oldest_first(self):
        cache = LocalVerdictCache(char_budget=600)
        big = PolicyDecision(
            action=PolicyAction.TRANSFORM,
            transformed_content='x' * 100,
        )

        await cache.store('first', big)
        await cache.store('second', big)
        await cache.store('third', big)

        assert await cache.get('first') is None, 'oldest goes first'
        assert await cache.get('third') is not None
