"""How long the caller waits for a real answer, per turn.

Pipecat's ``UserBotLatencyObserver`` stops the clock at the first bot audio.
On a tool turn that is usually the "One sec" filler, so it hides the wait the
caller actually feels. This observer stops the clock at the first audio that
came from the LLM after the turn's last tool result. Fillers are spoken
straight from ``TTSSpeakFrame`` and never pass through the LLM, so they never
count.

A turn runs from the caller's turn ending to the next turn starting (or the
call ending). Turns the bot never answered (an interruption, a hang-up) are
dropped.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    FunctionCallInProgressFrame,
    FunctionCallResultFrame,
    LLMTextFrame,
    TTSAudioRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

from call_processing.log.logger import logger


@dataclass(frozen=True)
class TurnLatency:
    """One answered turn: seconds from the caller's turn ending to the answer."""

    answer_secs: float
    # Tool name -> seconds the tool ran (summed when it ran more than once)
    tool_secs: Dict[str, float] = field(default_factory=dict)

    @property
    def used_tool(self) -> bool:
        return bool(self.tool_secs)


class TurnLatencyTracker:
    """Pure timing logic; times are passed in so tests can drive it."""

    def __init__(self) -> None:
        self._reset()

    def _reset(self) -> None:
        self._user_stopped_at: Optional[float] = None
        self._tool_starts: Dict[str, Tuple[str, float]] = {}
        self._tool_secs: Dict[str, float] = {}
        self._last_tool_end: Optional[float] = None
        # Audio that followed LLM text; the answer is the first one after the
        # last tool result
        self._llm_audio_times: List[float] = []
        self._awaiting_llm_audio = False

    @property
    def turn_open(self) -> bool:
        return self._user_stopped_at is not None

    def user_stopped(self, at: float) -> Optional[TurnLatency]:
        """The caller's turn ended. Closes any open turn first."""
        closed = self.close()
        self._user_stopped_at = at
        return closed

    def tool_started(self, call_id: str, name: str, at: float) -> None:
        if self.turn_open:
            self._tool_starts[call_id] = (name, at)

    def tool_finished(self, call_id: str, at: float) -> None:
        started = self._tool_starts.pop(call_id, None)
        if started is None:
            return
        name, started_at = started
        self._tool_secs[name] = self._tool_secs.get(name, 0.0) + (at - started_at)
        self._last_tool_end = at

    def llm_text(self) -> None:
        if self.turn_open:
            self._awaiting_llm_audio = True

    def audio(self, at: float) -> None:
        if self._awaiting_llm_audio:
            self._llm_audio_times.append(at)
            self._awaiting_llm_audio = False

    def close(self) -> Optional[TurnLatency]:
        """End the open turn. Returns its latency, or None if it was never answered."""
        if self._user_stopped_at is None:
            return None
        since = self._last_tool_end if self._last_tool_end is not None else 0.0
        answer_at = next((t for t in self._llm_audio_times if t >= since), None)
        result = None
        if answer_at is not None:
            result = TurnLatency(
                answer_secs=answer_at - self._user_stopped_at,
                tool_secs=dict(self._tool_secs),
            )
        self._reset()
        return result


class TurnLatencyObserver(BaseObserver):
    """Feeds pipeline frames to a ``TurnLatencyTracker`` and reports each turn."""

    def __init__(
        self,
        on_turn: Callable[[TurnLatency], Any],
        clock: Callable[[], float] = time.monotonic,
        **kwargs,
    ):
        super().__init__(observe_every_push=False, **kwargs)
        self._tracker = TurnLatencyTracker()
        self._on_turn = on_turn
        self._clock = clock

    async def on_push_frame(self, data: FramePushed):
        frame = data.frame
        now = self._clock()
        if isinstance(frame, UserStoppedSpeakingFrame):
            self._report(self._tracker.user_stopped(now))
        elif isinstance(frame, (UserStartedSpeakingFrame, EndFrame, CancelFrame)):
            self._report(self._tracker.close())
        elif isinstance(frame, FunctionCallInProgressFrame):
            self._tracker.tool_started(frame.tool_call_id, frame.function_name, now)
        elif isinstance(frame, FunctionCallResultFrame):
            self._tracker.tool_finished(frame.tool_call_id, now)
        elif isinstance(frame, LLMTextFrame):
            self._tracker.llm_text()
        elif isinstance(frame, TTSAudioRawFrame):
            self._tracker.audio(now)

    def _report(self, turn: Optional[TurnLatency]) -> None:
        if turn is None:
            return
        tools = ', '.join(f'{n}={s:.3f}s' for n, s in turn.tool_secs.items())
        logger.info(
            f'Turn latency: answer={turn.answer_secs:.3f}s'
            + (f' tools=[{tools}]' if tools else '')
        )
        self._on_turn(turn)


def latency_summary(turns: List[TurnLatency]) -> Dict[str, float]:
    """Per-call medians and maxima, as OTel attributes for the call span."""
    summary: Dict[str, float] = {}
    for prefix, group in (
        ('call.turn_latency', turns),
        ('call.tool_turn_latency', [t for t in turns if t.used_tool]),
    ):
        if not group:
            continue
        answers = [t.answer_secs for t in group]
        summary[f'{prefix}_count'] = len(answers)
        summary[f'{prefix}_p50_secs'] = round(statistics.median(answers), 3)
        summary[f'{prefix}_max_secs'] = round(max(answers), 3)
    tool_secs = [s for t in turns for s in t.tool_secs.values()]
    if tool_secs:
        summary['call.tool_exec_p50_secs'] = round(statistics.median(tool_secs), 3)
        summary['call.tool_exec_max_secs'] = round(max(tool_secs), 3)
    return summary
