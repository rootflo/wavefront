"""Cold start: loading a provider's model must not be charged to a request.

Presidio builds a spaCy model the first time it evaluates anything, and that
takes seconds. The engine runs every adapter call under
``AdapterSpec.timeout_seconds``, which defaults to 5 and is sized for checking
a message rather than for loading a model. So the first checked request after a
restart timed out, and under a FAIL_CLOSED policy was rejected outright — the
user saw "Safety checks could not be completed just now" on a healthy server.

Two things fix it. The model is built at startup, where nothing is waiting on
it. And a build is owned by the adapter rather than by whichever caller
happened to trigger it, so a caller cancelled by a timeout cannot throw away a
model that finished loading.

Needs no Presidio install: the build itself is stubbed, because what is under
test is who owns it and what survives a cancellation.
"""

import asyncio

import pytest

from flo_ai.guardrails import (
    AdapterSpec,
    EnforcementMode,
    GuardrailsEngine,
    PolicyAction,
    Principal,
    ResolvedPolicy,
    StaticPolicyResolver,
    WorkflowStage,
)
from flo_ai.guardrails.adapters.base_adapter import BaseAdapter
from flo_ai.guardrails.adapters.presidio_adapter import PresidioAdapter

BEFORE = WorkflowStage.BEFORE_MODEL
ACME = Principal(namespace='acme')


class SlowBuildAdapter(PresidioAdapter):
    """A Presidio adapter whose model load is slow, faked, and countable."""

    def __init__(self, build_seconds=0.2, fail_times=0, **kwargs):
        super().__init__(**kwargs)
        self.build_seconds = build_seconds
        self.fail_times = fail_times
        self.builds = 0

    async def _build_engines(self):
        self.builds += 1
        await asyncio.sleep(self.build_seconds)
        if self.builds <= self.fail_times:
            raise RuntimeError('spaCy model missing')
        self._analyzer, self._anonymizer = f'analyzer-{self.builds}', 'anonymizer'


class CountingAdapter(BaseAdapter):
    def __init__(self, name='counting', warmup_error=None):
        self._name = name
        self.warmups = 0
        self.warmup_error = warmup_error

    @property
    def name(self):
        return self._name

    async def warmup(self):
        self.warmups += 1
        if self.warmup_error:
            raise self.warmup_error

    async def evaluate(self, request):
        return self._allow()


class TestACancelledCallerCannotDiscardTheBuild:
    async def test_the_model_survives_a_timed_out_caller(self):
        """The bug behind the restart error.

        The engine cancels the caller when a check overruns. The cancellation
        used to land on the await holding the build, skipping the assignment
        that publishes it — so the executor thread finished loading the model
        and the result was dropped on the floor.
        """
        adapter = SlowBuildAdapter(build_seconds=0.2)

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(adapter._engines(), timeout=0.02)

        analyzer, _ = await adapter._engines()

        assert analyzer == 'analyzer-1', 'the finished build must be kept'
        assert adapter.builds == 1, 'and must not be started over'

    async def test_repeated_timeouts_do_not_stack_up_builds(self):
        """Each abandoned build kept one of only two Presidio worker threads,
        so real checks ended up queued behind loads nobody awaited."""
        adapter = SlowBuildAdapter(build_seconds=0.2)

        for _ in range(5):
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(adapter._engines(), timeout=0.01)

        await adapter._engines()

        assert adapter.builds == 1

    async def test_concurrent_callers_share_one_build(self):
        adapter = SlowBuildAdapter(build_seconds=0.05)

        results = await asyncio.gather(*(adapter._engines() for _ in range(4)))

        assert adapter.builds == 1
        assert {analyzer for analyzer, _ in results} == {'analyzer-1'}

    async def test_a_warm_adapter_does_not_rebuild(self):
        adapter = SlowBuildAdapter(build_seconds=0.01)

        await adapter._engines()
        await adapter._engines()

        assert adapter.builds == 1


class TestAFailedBuildIsRetried:
    async def test_the_next_call_tries_again(self):
        """A remembered failure would outlive its cause.

        The usual reason a build fails is a missing spaCy model. Caching that
        forever means an install that fixes it still needs a restart.
        """
        adapter = SlowBuildAdapter(build_seconds=0.01, fail_times=1)

        with pytest.raises(RuntimeError):
            await adapter._engines()
        analyzer, _ = await adapter._engines()

        assert analyzer == 'analyzer-2'
        assert adapter.builds == 2

    async def test_the_retry_works_immediately(self):
        """Regression on clearing the dead build from a done callback.

        Those run via call_soon, so a retry issued in the same tick as the
        failure still saw the dead task and replayed its error.
        """
        adapter = SlowBuildAdapter(build_seconds=0, fail_times=1)

        with pytest.raises(RuntimeError):
            await adapter._engines()
        await adapter._engines()  # no awaits in between

        assert adapter.builds == 2


class TestEngineWarmup:
    def engine(self, *adapters):
        return GuardrailsEngine(
            resolver=StaticPolicyResolver(
                ResolvedPolicy(
                    is_enabled=True,
                    mode=EnforcementMode.ENFORCE,
                    adapters=tuple(
                        AdapterSpec(name=a.name, stages=(BEFORE,)) for a in adapters
                    ),
                    version='v1',
                )
            ),
            adapters=list(adapters),
        )

    async def test_every_adapter_is_warmed(self):
        one, two = CountingAdapter('one'), CountingAdapter('two')

        await self.engine(one, two).warmup()

        assert (one.warmups, two.warmups) == (1, 1)

    async def test_a_failing_warmup_does_not_stop_the_server(self):
        """Startup must not hinge on a provider the policy may not even name.

        The adapter retries on first use, which is the behaviour there was
        before warming existed — so the worst case is the bug this fixes, not
        a server that will not boot.
        """
        broken = CountingAdapter('broken', warmup_error=RuntimeError('no model'))
        healthy = CountingAdapter('healthy')

        await self.engine(broken, healthy).warmup()  # must not raise

        assert healthy.warmups == 1, 'one bad provider must not skip the rest'

    async def test_warming_leaves_evaluation_working(self):
        adapter = CountingAdapter()
        engine = self.engine(adapter)

        await engine.warmup()
        decision = await engine.evaluate('hello', ACME, BEFORE)

        assert decision.action is PolicyAction.ALLOW

    async def test_the_default_warmup_is_a_no_op(self):
        """Most adapters have nothing to build; they must not have to say so."""

        class Bare(BaseAdapter):
            @property
            def name(self):
                return 'bare'

            async def evaluate(self, request):
                return self._allow()

        await Bare().warmup()

    async def test_a_warmed_presidio_adapter_does_not_build_on_evaluate(self):
        """What the startup call actually buys: the first request pays nothing."""
        adapter = SlowBuildAdapter(build_seconds=0.01)

        await adapter.warmup()
        builds_after_warmup = adapter.builds
        await adapter._engines()

        assert builds_after_warmup == 1
        assert adapter.builds == 1
