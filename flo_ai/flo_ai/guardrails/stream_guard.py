"""Deciding how much of a streamed response may be released, and when.

Streaming and output checks are in tension: a chunk already delivered cannot
be recalled. The simple resolution is to collect the whole response, vet it,
and only then release — correct, and it makes time-to-first-token equal
time-to-last-token, which is the same as not streaming at all.

This module implements the less simple resolution. Two guarantees are on
offer, and which one applies is decided per policy by the engine, never here:

**Buffered** — no character reaches the consumer before the final verdict.
Unconditional, and the only honest option when a provider's verdict is a
property of the whole passage: toxicity read from half a paragraph is not a
partial answer, it is a different question.

**Incremental** — a character reaches the consumer only once a scan has seen
it *and* the ``MARGIN`` characters that follow it, and found it clean. The
margin is what makes this equivalent to the buffered guarantee rather than
weaker than it. An entity of maximum length ``L`` that starts before the
release cut ends at most ``L`` characters later, so if ``MARGIN >= L`` it was
complete in the scanned text and therefore detectable, and the scan's silence
about it means it is not there. Adapters only ever get ``INCREMENTAL`` for
entity types where that bound holds — see ``INCREMENTAL_SAFE`` in
``adapters/pii_catalog.py``, which exists precisely to keep ``L <= MARGIN``
true by construction.

Retraction is the backstop, not the mechanism, and it should stay rare enough
to be worth a warning when it happens. It is reached when the terminal verdict
blocks a response some of which is already out, and when a scan changes its
mind about text already released — which a span-local detector should not do,
but Presidio is not perfectly monotonic (a score can shift, and a sentence
boundary can move, as more text arrives). The divergence check in
``_release_incremental`` catches that case whatever caused it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from flo_ai.utils.logger import logger

from .contracts import PolicyDecision, StreamMode

#: Characters withheld from the end of the scanned text before releasing the
#: rest. The binding constraint is the longest entity type that incremental
#: release is ever allowed to run on: EMAIL_ADDRESS at the RFC 5321 maximum of
#: 320 characters. Everything else in INCREMENTAL_SAFE is far shorter --
#: CREDIT_CARD ~24 with separators, IBAN_CODE 34, IP_ADDRESS 45 for IPv6,
#: CRYPTO ~62, PHONE_NUMBER ~20, US_SSN 11, IN_AADHAAR 14.
#:
#: No allowance is needed for trailing context: presidio-analyzer's
#: LemmaContextAwareEnhancer defaults context_suffix_count to 0, and its
#: context_prefix_count of 5 words looks *backwards*, into text the prefix
#: already contains.
#:
#: This constant and INCREMENTAL_SAFE are one mechanism expressed in two
#: places. Changing either means re-checking the other; a test asserts the
#: relation so that the reminder is not merely this comment.
DEFAULT_MARGIN_CHARS = 384

#: New characters required before a scan is worth running. Scans of a growing
#: prefix are strictly additional work -- every prefix is a distinct verdict
#: cache key, so no prefix scan ever saves the terminal scan anything -- and
#: Presidio runs on a two-thread executor. Stepping by this much bounds a 4 kB
#: response to roughly fifteen extra analyses instead of one per token.
DEFAULT_MIN_NEW_CHARS = 256

#: Floor on the gap between scans, so a fast provider burst cannot queue one
#: scan per chunk.
DEFAULT_MIN_INTERVAL_SECONDS = 0.25

#: How far back to look for a sentence boundary to cut on. Presidio is not
#: strictly span-local: the analyzer runs a spaCy pipeline, so NER over a
#: truncated final sentence can differ from the same text with the sentence
#: closed. Cutting on a boundary keeps whole sentences in the released region,
#: and makes a retract less jarring to read when one does happen.
SEGMENT_LOOKBACK_CHARS = 200

#: Key identifying a control chunk on the SDK's stream. Deliberately not
#: 'content': a consumer that reads chunks with ``chunk.get('content')`` --
#: which is what every consumer in this repo does -- then ignores the control
#: chunk rather than *appending* a replacement to the very text it replaces.
GUARDRAIL_CONTROL_KEY = 'guardrail'

#: (content, terminal) -> decision. The guard is given this rather than the
#: engine so that the state machine can be tested against scripted verdicts,
#: with no engine, policy or adapter in the way -- and so the one place where
#: a prefix scan differs from the final one (it is neither cached nor audited)
#: is visible at the call site instead of buried in here.
Evaluate = Callable[[str, bool], Awaitable[PolicyDecision]]


def control_chunk(
    action: str, message: str, replacement: Optional[str] = None
) -> Dict[str, Any]:
    """A chunk carrying a policy instruction rather than model output."""
    return {
        GUARDRAIL_CONTROL_KEY: {
            'action': action,
            'message': message,
            'replacement': replacement,
        }
    }


def is_control_chunk(chunk: Any) -> bool:
    return isinstance(chunk, dict) and GUARDRAIL_CONTROL_KEY in chunk


def chunk_text(chunk: Any) -> str:
    """The model-visible text in a chunk, or '' if it carries none."""
    if isinstance(chunk, dict):
        value = chunk.get('content')
        return value if isinstance(value, str) else ''
    return chunk if isinstance(chunk, str) else ''


@dataclass(frozen=True)
class StreamAction:
    """What the driver should do with what it just fed in."""

    #: Release these, in this order.
    chunks: Tuple[Dict[str, Any], ...] = ()
    #: Everything released so far is withdrawn; render ``replacement`` instead.
    retract: bool = False
    replacement: Optional[str] = None
    #: The caller should raise; the response is refused.
    blocked: bool = False
    #: Populated on a terminal verdict, for logging and for the refusal text.
    decision: Optional[PolicyDecision] = None


@dataclass
class _Opaque:
    """A chunk carrying no text: tool-call deltas, usage, finish reasons.

    ``plain_len`` is how much text had arrived when it did, which is what
    decides where it goes back in the sequence. The wrapper has no business
    dropping these -- that is the difference between being transparent and
    being a silent filter -- and the old buffered transform path dropped every
    one of them.
    """

    chunk: Dict[str, Any]
    plain_len: int


#: Shared "nothing to release" result. StreamAction is frozen, so one
#: instance is safe to hand back from every quiet path.
NOTHING = StreamAction()


class StreamGuard:
    """Tracks a streamed response and decides what may be released.

    One object serves all four modes, so there is no second code path to
    drift. That is also what fixes the dropped-metadata bug in buffered mode
    for free: ordering is tracked in one place regardless of when text leaves.
    """

    def __init__(
        self,
        evaluate: Evaluate,
        mode: StreamMode,
        *,
        margin: int = DEFAULT_MARGIN_CHARS,
        min_new_chars: int = DEFAULT_MIN_NEW_CHARS,
        min_interval_seconds: float = DEFAULT_MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if mode is StreamMode.PASSTHROUGH:
            raise ValueError('PASSTHROUGH needs no guard; do not construct one for it')
        self._evaluate = evaluate
        self._mode = mode
        self._margin = margin
        self._min_new_chars = min_new_chars
        self._min_interval = min_interval_seconds
        self._clock = clock

        #: Everything the model has produced, as plain text.
        self._text = ''
        #: Exactly the characters handed downstream, in vetted space -- which
        #: is not the same as a prefix of ``_text`` once a redaction applies.
        self._released = ''
        #: How much of ``_text`` counts as gone, for ordering opaque chunks.
        #: Approximate under an active redaction, which is acceptable: no
        #: opaque chunk carries user-visible text.
        self._released_plain = 0
        self._opaque: List[_Opaque] = []
        #: Where the first text chunk sat, so a buffered transform can put its
        #: single replacement chunk back in that position.
        self._first_text_at: Optional[int] = None

        self._scanned_at_len = 0
        self._last_scan_started = float('-inf')

    # -- what the driver sees --------------------------------------------

    @property
    def released_text(self) -> str:
        """What the consumer has actually seen. Empty means nothing escaped."""
        return self._released

    # -- feeding ---------------------------------------------------------

    async def feed(self, chunk: Dict[str, Any]) -> StreamAction:
        """Take one chunk from the provider; get back what may be released."""
        text = chunk_text(chunk)
        if text:
            if self._first_text_at is None:
                self._first_text_at = len(self._opaque)
            self._text += text
        else:
            self._opaque.append(_Opaque(chunk=chunk, plain_len=len(self._text)))

        if self._mode is StreamMode.OBSERVE:
            # Nothing is withheld in monitor mode, so there is nothing for a
            # prefix scan to inform. The one terminal evaluation still runs,
            # for the log line and the audit row that monitoring exists for.
            return self._release_verbatim(chunk)

        if self._mode is StreamMode.BUFFERED:
            return NOTHING

        if not self._should_scan():
            return NOTHING
        return await self._scan_and_release()

    async def finish(self) -> StreamAction:
        """Close the stream: run the terminal verdict and flush."""
        if not self._text:
            # No text means nothing to judge. Flush whatever metadata arrived
            # and stay silent -- evaluating '' would put an empty payload
            # through the adapters and an ALLOW row into the audit trail for a
            # response that never existed.
            return StreamAction(chunks=self._drain_opaque())

        decision = await self._evaluate(self._text, True)

        if decision.blocked:
            return StreamAction(
                retract=bool(self._released),
                blocked=True,
                decision=decision,
            )

        vetted = decision.transformed_content if decision.transformed else self._text

        if self._mode is StreamMode.OBSERVE:
            # Already released verbatim, and monitor mode applies nothing.
            return StreamAction(decision=decision)

        if self._mode is StreamMode.BUFFERED:
            return StreamAction(chunks=self._buffered_flush(vetted), decision=decision)

        return self._release_incremental(vetted, terminal=True, decision=decision)

    # -- release strategies ----------------------------------------------

    def _release_verbatim(self, chunk: Dict[str, Any]) -> StreamAction:
        text = chunk_text(chunk)
        if text:
            self._released += text
            self._released_plain = len(self._text)
        else:
            # Keep the bookkeeping honest even though everything flows: the
            # opaque chunk was appended by feed() and is going out right now.
            self._opaque.pop()
        return StreamAction(chunks=(chunk,))

    def _buffered_flush(self, vetted: str) -> Tuple[Dict[str, Any], ...]:
        """Everything at once, with the metadata still in its place."""
        pivot = self._first_text_at if self._first_text_at is not None else 0
        before = tuple(item.chunk for item in self._opaque[:pivot])
        after = tuple(item.chunk for item in self._opaque[pivot:])
        self._opaque = []
        self._released = vetted
        self._released_plain = len(self._text)
        text_chunks: Tuple[Dict[str, Any], ...] = (
            ({'content': vetted},) if vetted else ()
        )
        return before + text_chunks + after

    def _release_incremental(
        self,
        vetted: str,
        *,
        terminal: bool,
        decision: Optional[PolicyDecision] = None,
    ) -> StreamAction:
        # A redaction changed something already released. Nothing about the
        # margin can prevent this -- it is the detector changing its mind, not
        # an entity straddling the cut -- so the consumer is told to withdraw
        # what it has and render the corrected text instead.
        if not vetted.startswith(self._released):
            logger.warning(
                'Guardrail revised text already released '
                f'({len(self._released)} chars); retracting. A redaction '
                'should have been caught before release, so this is worth '
                'investigating rather than expected.'
            )
            # Clamped to the vetted text, which the usual cut does not have
            # to be: a redaction that shortens the response drastically -- a
            # whole reply replaced by a refusal, say -- leaves the ordinary
            # offset pointing past the end of what there now is to release.
            cut = (
                len(vetted) if terminal else max(0, min(self._cut(vetted), len(vetted)))
            )
            self._released = vetted[:cut]
            self._released_plain = min(cut, len(self._text))
            return StreamAction(
                chunks=self._drain_opaque() if terminal else (),
                retract=True,
                replacement=self._released,
                decision=decision,
            )

        cut = len(vetted) if terminal else self._cut(vetted)
        if cut <= len(self._released):
            return StreamAction(
                chunks=self._drain_opaque() if terminal else (),
                decision=decision,
            )

        # Metadata that arrived before the text being released now goes first,
        # the rest after, so a finish_reason cannot precede what it terminates.
        before = self._take_opaque(self._released_plain)
        addition = vetted[len(self._released) : cut]
        self._released = vetted[:cut]
        self._released_plain = min(cut, len(self._text))
        after = (
            self._drain_opaque()
            if terminal
            else self._take_opaque(self._released_plain)
        )
        return StreamAction(
            chunks=before + ({'content': addition},) + after, decision=decision
        )

    # -- scanning --------------------------------------------------------

    def _should_scan(self) -> bool:
        # Below margin + min_new_chars nothing could be released even if the
        # scan came back clean, so running one is pure cost. This single
        # condition is what keeps short replies -- the common case -- at
        # exactly one scan, the same as buffered mode.
        if len(self._text) < self._margin + self._min_new_chars:
            return False
        if len(self._text) - self._scanned_at_len < self._min_new_chars:
            return False
        if self._clock() - self._last_scan_started < self._min_interval:
            return False
        return True

    async def _scan_and_release(self) -> StreamAction:
        text = self._text
        self._scanned_at_len = len(text)
        self._last_scan_started = self._clock()

        decision = await self._evaluate(text, False)

        # An adapter error is not a clean vet. Fail-open at the end is a
        # deliberate choice, made once, with the whole response in hand and an
        # audit row to show for it; fail-open here would be that choice made
        # silently and repeatedly, about text nothing ever looked at. So an
        # outage degrades incremental release to buffered, which is the safe
        # direction, and the next trigger retries -- error verdicts are not
        # cached.
        if any(result.is_error for result in decision.results):
            return NOTHING

        # A block caused by the checks failing rather than by the content must
        # not end the stream: a transient timeout under FAIL_CLOSED would kill
        # a response the provider may well vet successfully at the end.
        if decision.blocked and not decision.blocked_by_failure:
            return StreamAction(
                retract=bool(self._released), blocked=True, decision=decision
            )

        vetted = decision.transformed_content if decision.transformed else text
        return self._release_incremental(vetted, terminal=False)

    # -- cut -------------------------------------------------------------

    def _cut(self, vetted: str) -> int:
        """How far into ``vetted`` it is safe to release.

        Held back from whichever of the plaintext and the vetted text is
        shorter. A redaction changes length in either direction -- replace and
        redact shorten, mask preserves, hash expands to 64 hex characters --
        so the plaintext offset is not an index into ``vetted`` at all. Rather
        than invent a mapping between the two, take the more conservative of
        the two candidates: it is at least as strict as either, and the
        divergence check above is what actually carries soundness here.
        """
        cut = min(len(self._text), len(vetted)) - self._margin
        if cut <= len(self._released):
            return len(self._released)
        return self._snap(vetted, cut)

    def _snap(self, vetted: str, cut: int) -> int:
        """Pull ``cut`` back to a sentence boundary, if one is near enough."""
        floor = max(len(self._released), cut - SEGMENT_LOOKBACK_CHARS)
        for index in range(cut - 1, floor - 1, -1):
            char = vetted[index]
            if char == '\n':
                return index + 1
            if (
                char in '.!?'
                and index + 1 < len(vetted)
                and vetted[index + 1].isspace()
            ):
                return index + 1
        return cut

    # -- opaque chunk bookkeeping ----------------------------------------

    def _take_opaque(self, plain_len: int) -> Tuple[Dict[str, Any], ...]:
        ready = [item for item in self._opaque if item.plain_len <= plain_len]
        if not ready:
            return ()
        self._opaque = [item for item in self._opaque if item.plain_len > plain_len]
        return tuple(item.chunk for item in ready)

    def _drain_opaque(self) -> Tuple[Dict[str, Any], ...]:
        drained = tuple(item.chunk for item in self._opaque)
        self._opaque = []
        return drained
