"""The release state machine, exercised without an engine.

Every test here drives ``StreamGuard`` with a scripted verdict function and a
fake clock, so what is under test is the decision about *when* text may leave
and nothing else -- no policy resolution, no adapter, no provider.

The margin and step are shrunk from their production values throughout. The
arithmetic is identical at any size and 20 characters fit on a line.
"""

import pytest

from flo_ai.guardrails.contracts import (
    AssessmentStatus,
    CheckResult,
    FailureClass,
    PolicyAction,
    PolicyDecision,
    StreamMode,
)
from flo_ai.guardrails.stream_guard import (
    GUARDRAIL_CONTROL_KEY,
    StreamGuard,
    control_chunk,
    is_control_chunk,
)

CARD = '4111111111111111'
CARD_REDACTED = '[CARD]'

MARGIN = 20
MIN_NEW = 10


# -- scripted verdicts ---------------------------------------------------


def allow():
    return PolicyDecision()


def transform(to):
    return PolicyDecision(
        action=PolicyAction.TRANSFORM,
        transformed_content=to,
        results=[
            CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.TRANSFORM,
                adapter='scripted',
                transformed_content=to,
            )
        ],
    )


def block():
    return PolicyDecision(
        action=PolicyAction.BLOCK,
        results=[
            CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.BLOCK,
                adapter='scripted',
                message='refused',
            )
        ],
    )


def adapter_error_open():
    """An outage the policy chose to let through. ALLOW, but not a clean vet."""
    return PolicyDecision(
        action=PolicyAction.ALLOW,
        results=[
            CheckResult(
                status=AssessmentStatus.ERROR,
                action=PolicyAction.ALLOW,
                adapter='scripted',
                failure_class=FailureClass.INFRASTRUCTURE,
                message='provider timed out',
            )
        ],
    )


def adapter_error_closed():
    """The same outage under FAIL_CLOSED: a block, but not about the content."""
    return PolicyDecision(
        action=PolicyAction.BLOCK,
        results=[
            CheckResult(
                status=AssessmentStatus.ERROR,
                action=PolicyAction.BLOCK,
                adapter='scripted',
                failure_class=FailureClass.INFRASTRUCTURE,
                message='provider timed out',
            )
        ],
    )


def monitored(inner):
    """What ``_decide`` produces in MONITOR mode: a verdict nobody acts on."""
    decision = inner()
    return PolicyDecision(
        action=PolicyAction.ALLOW,
        results=decision.results,
        transformed_content=decision.transformed_content,
        enforced=False,
        observed_action=decision.action,
    )


def redacting(secret=CARD, placeholder=CARD_REDACTED):
    """Verdict function that redacts like a span-local PII adapter would."""

    def verdict(content, terminal):
        if secret in content:
            return transform(content.replace(secret, placeholder))
        return allow()

    return verdict


class Clock:
    """Monotonic fake. Steps far enough that the debounce never interferes."""

    def __init__(self, step=1.0):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


class Scripted:
    """Records what it was asked, so scan counts can be asserted."""

    def __init__(self, verdict=None):
        self._verdict = verdict or (lambda content, terminal: allow())
        self.calls = []

    async def __call__(self, content, terminal):
        self.calls.append((content, terminal))
        return self._verdict(content, terminal)

    @property
    def prefix_scans(self):
        return [content for content, terminal in self.calls if not terminal]

    @property
    def terminal_scans(self):
        return [content for content, terminal in self.calls if terminal]


def build(verdict=None, mode=StreamMode.INCREMENTAL, **kwargs):
    evaluate = verdict if isinstance(verdict, Scripted) else Scripted(verdict)
    guard = StreamGuard(
        evaluate,
        mode,
        margin=kwargs.pop('margin', MARGIN),
        min_new_chars=kwargs.pop('min_new_chars', MIN_NEW),
        min_interval_seconds=kwargs.pop('min_interval_seconds', 0.0),
        clock=kwargs.pop('clock', Clock()),
        **kwargs,
    )
    return guard, evaluate


class Run:
    """The observable result of driving a guard to completion."""

    def __init__(self):
        self.chunks = []
        self.retractions = []
        self.blocked = None
        #: Released text as it looked after each feed, for "was this ever
        #: visible" assertions that a final-state check would miss.
        self.snapshots = []

    @property
    def text(self):
        return ''.join(chunk['content'] for chunk in self.chunks if 'content' in chunk)


async def drive(guard, chunks):
    run = Run()
    for chunk in chunks:
        action = await guard.feed(chunk)
        _collect(run, action)
        run.snapshots.append(guard.released_text)
        if action.blocked:
            return run
    _collect(run, await guard.finish())
    return run


def _collect(run, action):
    if action.retract:
        run.retractions.append(action.replacement)
        if not action.blocked:
            # What the driver does: the retract goes out as a control chunk,
            # and anything already shown is discarded.
            run.chunks = []
    run.chunks.extend(action.chunks)
    if action.blocked:
        run.blocked = action


def as_chunks(text, size):
    return [{'content': text[i : i + size]} for i in range(0, len(text), size)]


# -- the guarantee -------------------------------------------------------


class TestNothingEscapesEarly:
    """The invariant: no character of an entity is released before detection."""

    async def test_entity_split_across_chunks(self):
        guard, script = build(redacting())
        prefix = 'here is a long preamble that pads the response out. '
        chunks = [{'content': prefix}, {'content': 'card 41111'}]
        chunks += [{'content': '11111111111 and more text follows here.'}]

        run = await drive(guard, chunks)

        assert CARD not in run.text
        assert CARD_REDACTED in run.text
        for seen in run.snapshots:
            assert '41111' not in seen, 'a card fragment reached the consumer'

    async def test_entity_straddling_the_release_cut(self):
        """The cut must land before an entity that is not yet complete."""
        # Positioned so the card starts inside the held-back margin.
        head = 'x' * 60
        guard, script = build(redacting())

        await guard.feed({'content': head + 'card ' + CARD[:8]})
        released_before = guard.released_text

        assert '4111' not in released_before
        assert released_before == head[: len(released_before)]

    async def test_stream_ends_mid_entity(self):
        """A truncated card is not a card; only the terminal verdict rules."""
        guard, script = build(redacting())
        text = 'y' * 60 + ' card 41111111'

        run = await drive(guard, as_chunks(text, 8))

        assert run.text == text, 'nothing matched, so nothing should change'
        assert run.blocked is None

    async def test_released_text_is_never_unvetted(self):
        """Every released character appeared in some completed scan."""
        guard, script = build(redacting())
        text = 'z' * 200

        run = await drive(guard, as_chunks(text, 7))

        for seen in run.snapshots:
            if not seen:
                continue
            assert any(
                scanned.startswith(seen) for scanned, _ in script.calls
            ), 'released text that no scan had covered'


class TestDivergence:
    async def test_retroactive_redaction_retracts_once(self):
        """A verdict that changes its mind about released text must retract."""
        clean_prefix = 'a' * 80

        def verdict(content, terminal):
            # Only at the end does the adapter decide the opening was PII --
            # exactly the non-monotonic behaviour the check exists for.
            if terminal:
                return transform(content.replace('a' * 10, 'REDACTED', 1))
            return allow()

        guard, script = build(verdict)
        run = await drive(guard, as_chunks(clean_prefix, 9))

        assert len(run.retractions) == 1
        assert run.retractions[0].startswith('REDACTED')
        assert guard.released_text == run.retractions[0]
        assert 'a' * 10 not in guard.released_text[: len('REDACTED')]

    async def test_expanding_redaction_never_outruns_the_vetted_text(self):
        """A hash-style rewrite lengthens; the cut must stay inside it."""

        def verdict(content, terminal):
            if 'SEED' in content:
                return transform(content.replace('SEED', 'H' * 64))
            return allow()

        guard, script = build(verdict)
        text = 'b' * 40 + 'SEED' + 'c' * 60

        run = await drive(guard, as_chunks(text, 11))

        assert 'SEED' not in run.text
        assert run.text == text.replace('SEED', 'H' * 64)


class TestBlocking:
    async def test_content_block_on_a_prefix_stops_the_stream(self):
        consumed = []

        def verdict(content, terminal):
            return block() if 'STOP' in content else allow()

        guard, script = build(verdict)
        chunks = as_chunks('d' * 60 + 'STOP' + 'e' * 200, 10)

        run = Run()
        for chunk in chunks:
            consumed.append(chunk)
            action = await guard.feed(chunk)
            _collect(run, action)
            if action.blocked:
                break

        assert run.blocked is not None
        assert len(consumed) < len(chunks), 'provider was still being drained'

    async def test_block_reports_whether_anything_escaped(self):
        def verdict(content, terminal):
            return block() if terminal else allow()

        guard, script = build(verdict)
        run = await drive(guard, as_chunks('f' * 200, 10))

        assert run.blocked.blocked
        assert run.blocked.retract, 'text was released, so it must be withdrawn'

    async def test_block_with_nothing_released_does_not_retract(self):
        guard, script = build(lambda content, terminal: block())
        run = await drive(guard, as_chunks('short', 2))

        assert run.blocked.blocked
        assert not run.blocked.retract


class TestErrorsMidStream:
    async def test_fail_open_error_does_not_advance_the_cut(self):
        """An outage is not a clean vet, whatever action the policy applied."""
        state = {'failing': True}

        def verdict(content, terminal):
            if state['failing'] and not terminal:
                return adapter_error_open()
            return allow()

        guard, script = build(verdict)
        await guard.feed({'content': 'g' * 60})
        assert guard.released_text == '', 'released text on an errored scan'

        state['failing'] = False
        await guard.feed({'content': 'h' * 40})
        assert guard.released_text != '', 'a clean scan should release again'

    async def test_fail_closed_error_on_a_prefix_does_not_end_the_stream(self):
        """A transient timeout must not kill a response that vets fine."""

        def verdict(content, terminal):
            return allow() if terminal else adapter_error_closed()

        guard, script = build(verdict)
        text = 'i' * 200
        run = await drive(guard, as_chunks(text, 10))

        assert run.blocked is None
        assert run.text == text


class TestModes:
    async def test_observe_releases_immediately_and_applies_nothing(self):
        guard, script = build(
            lambda content, terminal: monitored(lambda: transform('<gone>')),
            mode=StreamMode.OBSERVE,
        )
        text = 'monitor me please'

        run = await drive(guard, as_chunks(text, 4))

        assert run.text == text, 'monitor mode must not rewrite anything'
        assert run.retractions == []
        assert script.prefix_scans == [], 'nothing is withheld, so nothing to scan'
        assert len(script.terminal_scans) == 1, 'the audit row still needs one'

    async def test_buffered_releases_nothing_until_the_end(self):
        guard, script = build(redacting(), mode=StreamMode.BUFFERED)
        chunks = as_chunks('j' * 100 + CARD, 9)

        run = Run()
        for chunk in chunks:
            action = await guard.feed(chunk)
            _collect(run, action)
            assert action.chunks == (), 'buffered mode released early'
        _collect(run, await guard.finish())

        assert CARD_REDACTED in run.text
        assert script.prefix_scans == []

    async def test_passthrough_needs_no_guard(self):
        with pytest.raises(ValueError):
            StreamGuard(Scripted(), StreamMode.PASSTHROUGH)


class TestCost:
    async def test_short_reply_costs_exactly_one_scan(self):
        """Below margin + step nothing could be released, so nothing is asked.

        This is the cost guarantee. It fails the moment someone drops the
        length precondition from ``_should_scan``.
        """
        guard, script = build()
        short = 'k' * (MARGIN + MIN_NEW - 1)

        await drive(guard, [{'content': short}])

        assert script.prefix_scans == []
        assert len(script.terminal_scans) == 1

    async def test_scan_count_is_bounded_by_the_step(self):
        guard, script = build()
        text = 'm' * 400

        await drive(guard, as_chunks(text, 1))

        assert len(script.prefix_scans) <= len(text) // MIN_NEW + 1

    async def test_debounce_suppresses_a_burst(self):
        """A fast provider must not queue one scan per chunk."""
        # A clock that barely moves, against the default quarter-second floor.
        guard, script = build(min_interval_seconds=0.25, clock=Clock(step=0.001))

        await drive(guard, as_chunks('n' * 400, 5))

        assert len(script.prefix_scans) <= 2


class TestChunkFidelity:
    async def test_non_content_chunks_survive(self):
        guard, script = build(mode=StreamMode.BUFFERED)
        usage = {'usage': {'tokens': 12}}

        run = await drive(guard, [{'content': 'hello '}, usage, {'content': 'world'}])

        assert usage in run.chunks
        assert run.text == 'hello world'

    async def test_non_content_chunks_survive_a_buffered_transform(self):
        """Regression: the transform path returned early and dropped these."""
        guard, script = build(redacting(), mode=StreamMode.BUFFERED)
        usage = {'usage': {'tokens': 12}}

        run = await drive(
            guard, [{'content': f'pay {CARD} '}, usage, {'content': 'now'}]
        )

        assert usage in run.chunks, 'metadata was dropped by the rewrite'
        assert run.text == f'pay {CARD_REDACTED} now'

    async def test_metadata_keeps_its_place_around_the_text(self):
        guard, script = build(mode=StreamMode.BUFFERED)
        first = {'role': 'assistant'}
        last = {'finish_reason': 'stop'}

        run = await drive(guard, [first, {'content': 'body'}, last])

        assert run.chunks.index(first) < run.chunks.index(last)
        assert run.chunks[0] is first
        assert run.chunks[-1] is last

    async def test_only_non_content_chunks(self):
        guard, script = build()
        chunks = [{'usage': {'tokens': 1}}, {'finish_reason': 'stop'}]

        run = await drive(guard, chunks)

        assert run.chunks == chunks
        assert script.calls == [], 'no text means nothing to evaluate'

    async def test_empty_stream(self):
        guard, script = build()

        run = await drive(guard, [])

        assert run.chunks == []
        assert script.calls == [], 'evaluating nothing would audit a non-event'

    @pytest.mark.parametrize('size', range(1, 18))
    async def test_total_fidelity_at_any_chunk_size(self, size):
        """However the provider splits it, the consumer gets it exactly once."""
        text = 'The quick brown fox. ' * 12 + f'Card {CARD}. Done.'
        guard, script = build(redacting())

        run = await drive(guard, as_chunks(text, size))

        assert run.text == text.replace(CARD, CARD_REDACTED)


class TestControlChunks:
    def test_a_control_chunk_carries_no_content_key(self):
        """So a consumer reading chunk['content'] ignores it, not appends it."""
        chunk = control_chunk('retract', 'withheld', replacement='clean')

        assert 'content' not in chunk
        assert is_control_chunk(chunk)
        assert chunk[GUARDRAIL_CONTROL_KEY]['replacement'] == 'clean'

    def test_ordinary_chunks_are_not_control_chunks(self):
        assert not is_control_chunk({'content': 'hi'})
        assert not is_control_chunk('hi')
        assert not is_control_chunk(None)
