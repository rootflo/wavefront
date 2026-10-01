"""The run scope survives a stream, and survives that stream being abandoned.

`run_scoped_stream` exists because of one specific failure. An async generator
has no context of its own -- it runs in the context of whoever resumes it. When
a client disconnects, Starlette cancels the task iterating the response body
while it is parked at a `yield`, so the generator is never resumed; asyncio's
finaliser then throws GeneratorExit into it from a *different task, and so a
different context*. A scope held across that `yield` resets its token there and
raises `ValueError: Token was created in a different Context`, which replaces
the GeneratorExit, misses the disconnect handler written to catch it, and loses
the partial reply that handler exists to save.

The abandonment test closes the generator from another task deliberately.
Closing it from the same task reproduces nothing: the token would be reset in
the context that created it and a scope spanning the yield would pass too.
"""

import asyncio

from flo_ai.guardrails.run_context import get_run_id

from common_module.utils.guardrails import guardrail_run_scope, run_scoped_stream


async def _ids(count=2):
    """Report the run id visible to the producer at each step."""
    for _ in range(count):
        yield get_run_id()


async def _forever():
    while True:
        yield 'chunk'


class TestRunScopedStream:
    async def test_the_producer_sees_the_bound_run_id(self):
        assert [x async for x in run_scoped_stream(_ids(), 'be-abc12345')] == [
            'be-abc12345',
            'be-abc12345',
        ]

    async def test_the_id_does_not_leak_to_the_consumer_between_items(self):
        # The scope belongs to the producer's step, not to the surrounding
        # code, or a later unrelated evaluation would be stamped with it.
        async for _ in run_scoped_stream(_ids(1), 'be-abc12345'):
            assert get_run_id() is None

    async def test_closing_from_another_task_does_not_raise(self):
        # The regression test. Parked at a yield, closed from elsewhere.
        stream = run_scoped_stream(_forever(), 'be-abc12345')
        assert await stream.__anext__() == 'chunk'

        await asyncio.create_task(stream.aclose())

    async def test_cancelling_mid_step_does_not_raise(self):
        async def _hangs():
            await asyncio.Event().wait()
            yield 'never'

        stream = run_scoped_stream(_hangs(), 'be-abc12345')
        task = asyncio.create_task(stream.__anext__())
        await asyncio.sleep(0.01)  # let it park inside the scope
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_an_empty_source_terminates_cleanly(self):
        async def _nothing():
            return
            yield  # pragma: no cover

        assert [x async for x in run_scoped_stream(_nothing(), 'be-abc12345')] == []


class TestGuardrailRunScope:
    def test_an_explicit_id_wins(self):
        with guardrail_run_scope('be-explicit1'):
            assert get_run_id() == 'be-explicit1'

    def test_it_falls_back_to_the_request_id(self):
        # Outside a request the middleware's default is what there is; the
        # point is that the scope binds *something* rather than leaving the
        # decision unattributable.
        with guardrail_run_scope():
            assert get_run_id() == 'NO-REQUEST-ID'

    def test_it_restores_the_previous_value(self):
        with guardrail_run_scope('be-outer0001'):
            with guardrail_run_scope('be-inner0001'):
                assert get_run_id() == 'be-inner0001'
            assert get_run_id() == 'be-outer0001'
        assert get_run_id() is None
