"""When the user's turn starts and ends: VAD, barge-in and end-of-turn timing.

Per agent, via ``conversation_config.turn_taking`` on the voice agent::

    {
      "turn_taking": {
        "barge_in": true,               // may the user interrupt the bot?
        "barge_in_min_words": 0,        // words to interrupt; 0 = on any sound
        "mute_until_first_bot_complete": false,  // welcome cannot be interrupted
        "vad_confidence": 0.75,         // 0-1, how sure VAD must be it is speech
        "vad_min_volume": 0.65,         // 0-1, ignore audio quieter than this
        "vad_start_ms": 200,            // speech needed before a turn can start
        "vad_stop_ms": 200,             // silence before Smart Turn is asked
        "end_of_turn_timeout_ms": 3000, // silence that ends a turn Smart Turn
                                        // still thinks is unfinished
        "transcript_turn_start": true,  // a transcript starts the turn when
                                        // VAD missed the speech
        "idle_timeout_ms": 0,           // caller silence before the bot checks
                                        // in; 0 = never (see user_idle.py)
        "idle_max_check_ins": 2,        // check-ins before a goodbye and hang-up
        "idle_fixed_goodbye": false,    // off: the LLM words the goodbye
        "idle_goodbye_message": "..."   // spoken as written when fixed
      }
    }

With ``barge_in`` on (the default) there are two ways to interrupt. ``barge_in_min_words`` of 1
or more waits for that many transcribed words: slower, but a cough or background
noise cannot cut the bot off. ``0`` interrupts as soon as VAD hears speech
(about 200 ms), before any word is transcribed: the fastest, and the most
easily triggered by noise or echo.

With ``barge_in`` off the bot always finishes what it is saying:
anything the user says meanwhile is dropped, except that a user still speaking
when the bot finishes gets their turn started then. The app's own interrupt
controls (orb tap, step changes) still work.

``mute_until_first_bot_complete`` ignores the user until the bot has finished its
welcome message, whatever the barge-in setting; after that, barge-in applies as
usual. It only takes effect for a bot that has a welcome message (otherwise the
bot would never speak first and the user would stay muted), and only for the
call's first agent, not for one swapped in mid-call.

``transcript_turn_start`` is the safety net for speech VAD misses (a short word
such as "Hindi", or a quiet caller) while the STT still transcribes it. Off, that
transcript waits unanswered until VAD hears the next utterance, and the bot sits
silent. Only a final transcript counts (an interim could be the noise the VAD
thresholds rejected), and not one landing within ``LATE_TRANSCRIPT_SECS`` of a
turn ending: that is the tail of the utterance just answered, not new speech.
With ``barge_in`` off it only starts a turn while the bot is silent.
``barge_in_min_words`` of 1 or more already starts turns from transcripts, so
there it changes nothing.

Noisy phone lines want a higher confidence / volume floor and more barge-in
words; a quiet browser can go lower for snappier interruptions. Every reply
waits at least ``vad_stop_ms``, so raise it only if the bot keeps answering
before the user has finished.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional

from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.turns.types import ProcessFrameResult
from pipecat.turns.user_mute import (
    BaseUserMuteStrategy,
    FunctionCallUserMuteStrategy,
    MuteUntilFirstBotCompleteUserMuteStrategy,
)
from pipecat.turns.user_start import (
    BaseUserTurnStartStrategy,
    MinWordsUserTurnStartStrategy,
    TranscriptionUserTurnStartStrategy,
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import (
    BaseUserTurnStopStrategy,
    TurnAnalyzerUserTurnStopStrategy,
)

from call_processing.services.common.conversation_config import (
    bounded_number,
    config_section,
)
from call_processing.services.common.smart_turn import SharedSmartTurnAnalyzer
from call_processing.services.common.user_idle import DEFAULT_IDLE_GOODBYE

_SECTION = 'conversation_config.turn_taking'
# A final transcript this soon after a user turn ended belongs to that turn (an
# STT that split one utterance in two), so it never starts a new one
LATE_TRANSCRIPT_SECS = 1.0
# Talk-over's final transcript lands within this long of the VAD stop; later
# than that a transcript is the user's own speech VAD missed
TALK_OVER_TRANSCRIPT_SECS = 2.0
_MIN_IDLE_TIMEOUT_MS = 2000


class _LateTranscriptGuard:
    """Remembers when the last user turn ended, for transcript turn starts."""

    _late_transcript_secs: float = LATE_TRANSCRIPT_SECS
    _turn_stopped_at: Optional[float] = None
    _user_turn_active: bool = False

    async def handle_user_turn_started(self):
        await super().handle_user_turn_started()
        self._user_turn_active = True

    async def handle_user_turn_stopped(self):
        await super().handle_user_turn_stopped()
        self._user_turn_active = False
        self._turn_stopped_at = time.monotonic()

    def _transcript_is_late(self) -> bool:
        return (
            self._turn_stopped_at is not None
            and time.monotonic() - self._turn_stopped_at < self._late_transcript_secs
        )

    async def _drop_if_late(self) -> bool:
        """Drop a late final: Pipecat already added its text to the aggregation,
        which would otherwise join the user's next turn. Not while a turn is
        active, whose own words are in that aggregation too."""
        if not self._transcript_is_late():
            return False
        if not self._user_turn_active:
            await self.trigger_reset_aggregation()
        return True


class TranscriptFallbackStartStrategy(
    _LateTranscriptGuard, TranscriptionUserTurnStartStrategy
):
    """A final transcript starts the turn when VAD missed the speech.

    Never an interim, and never a final that lands just after a turn ended (see
    ``LATE_TRANSCRIPT_SECS``): either would interrupt the bot for speech the
    user did not mean as a new turn.
    """

    def __init__(self, **kwargs):
        super().__init__(use_interim=False, **kwargs)

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, TranscriptionFrame) and await self._drop_if_late():
            return ProcessFrameResult.CONTINUE
        return await super().process_frame(frame)


class VADWhenBotSilentStartStrategy(_LateTranscriptGuard, VADUserTurnStartStrategy):
    """VAD starts the user's turn only while the bot is silent.

    Pipecat stops at the first start strategy that fires, so a plain VAD
    strategy listed before ``MinWordsUserTurnStartStrategy`` would always win
    and any noise would cut the bot off. While the bot speaks this defers to
    MinWords; while it is silent, VAD keeps turn starts instant.

    ``discard_talk_over``: no MinWords strategy follows (barge-in is off), so
    what the user says over the bot is thrown away instead of piling up into
    their next turn. If they are still speaking when the bot finishes, their
    turn starts then rather than waiting for the next pause.

    ``start_on_transcript``: while the bot is silent, a final transcript starts
    the turn too, for speech VAD missed (not one landing just after a turn
    ended, as for ``TranscriptFallbackStartStrategy``). Pipecat's own transcription strategy
    would also fire on talk-over, which barge-in off must ignore: the final
    transcript of talk-over that ended just before the bot did lands after it
    stops, so that one is dropped too.
    """

    def __init__(
        self,
        *,
        discard_talk_over: bool = False,
        start_on_transcript: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._discard_talk_over = discard_talk_over
        self._start_on_transcript = start_on_transcript
        self._bot_speaking = False
        self._talking_over = False
        # When talk-over last ended while the bot spoke; its final transcript is
        # due until then plus TALK_OVER_TRANSCRIPT_SECS
        self._talk_over_ended_at: Optional[float] = None

    def _talk_over_transcript_due(self) -> bool:
        return (
            self._talk_over_ended_at is not None
            and time.monotonic() - self._talk_over_ended_at < TALK_OVER_TRANSCRIPT_SECS
        )

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._talk_over_ended_at = None
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            if self._discard_talk_over and self._talking_over:
                self._talking_over = False
                self._talk_over_ended_at = None
                await self.trigger_user_turn_started()
                return ProcessFrameResult.STOP
        if self._bot_speaking:
            if self._discard_talk_over:
                if isinstance(frame, VADUserStartedSpeakingFrame):
                    self._talking_over = True
                elif isinstance(frame, VADUserStoppedSpeakingFrame):
                    self._talking_over = False
                    self._talk_over_ended_at = time.monotonic()
                elif isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
                    if isinstance(frame, TranscriptionFrame):
                        self._talk_over_ended_at = None
                    await self.trigger_reset_aggregation()
            return ProcessFrameResult.CONTINUE
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._talk_over_ended_at = None
        if self._start_on_transcript and isinstance(frame, TranscriptionFrame):
            if await self._drop_if_late():
                return ProcessFrameResult.CONTINUE
            if self._talk_over_transcript_due():
                self._talk_over_ended_at = None
                await self.trigger_reset_aggregation()
                return ProcessFrameResult.CONTINUE
            await self.trigger_user_turn_started()
            return ProcessFrameResult.STOP
        return await super().process_frame(frame)


@dataclass(frozen=True)
class TurnTakingConfig:
    # Off: the bot always finishes speaking.
    barge_in: bool = True
    # When barge-in is on: words needed to interrupt. 0 interrupts on VAD alone
    # (fastest). Two let "no wait" / "hold on" through while a cough or a single
    # misheard word does not cut the bot off.
    barge_in_min_words: int = 0
    # On: the welcome message plays to the end before the user is heard.
    mute_until_first_bot_complete: bool = False
    vad_confidence: float = 0.75
    vad_min_volume: float = 0.65
    vad_start_secs: float = 0.2
    # Pipecat's default; Smart Turn decides the rest, and the STT wait budget
    # assumes 0.2 s.
    vad_stop_secs: float = 0.2
    end_of_turn_timeout_secs: float = 3.0
    # Off: speech VAD misses goes unanswered until the user speaks again
    transcript_turn_start: bool = True
    # Off: the bot waits in silence for as long as it takes
    idle_timeout_secs: float = 0.0
    idle_max_check_ins: int = 2
    # Off: the LLM words the goodbye, in the conversation's language
    idle_fixed_goodbye: bool = False
    idle_goodbye_message: str = DEFAULT_IDLE_GOODBYE

    @classmethod
    def from_agent_config(cls, agent_config: Mapping[str, Any]) -> TurnTakingConfig:
        raw = config_section(agent_config, 'turn_taking')
        d = cls()

        def number(key, default, minimum, maximum):
            return bounded_number(
                raw, key, default, minimum=minimum, maximum=maximum, path=_SECTION
            )

        idle_timeout_ms = number(
            'idle_timeout_ms', d.idle_timeout_secs * 1000, 0, 60000
        )
        if 0 < idle_timeout_ms < _MIN_IDLE_TIMEOUT_MS:
            # A tiny timeout would check in on every breath
            idle_timeout_ms = _MIN_IDLE_TIMEOUT_MS
        idle_goodbye = raw.get('idle_goodbye_message')

        return cls(
            barge_in=raw['barge_in']
            if isinstance(raw.get('barge_in'), bool)
            else d.barge_in,
            mute_until_first_bot_complete=raw['mute_until_first_bot_complete']
            if isinstance(raw.get('mute_until_first_bot_complete'), bool)
            else d.mute_until_first_bot_complete,
            barge_in_min_words=int(
                number('barge_in_min_words', d.barge_in_min_words, 0, 10)
            ),
            vad_confidence=number('vad_confidence', d.vad_confidence, 0.3, 0.95),
            vad_min_volume=number('vad_min_volume', d.vad_min_volume, 0.0, 0.95),
            vad_start_secs=number('vad_start_ms', d.vad_start_secs * 1000, 50, 1000)
            / 1000,
            vad_stop_secs=number('vad_stop_ms', d.vad_stop_secs * 1000, 100, 2000)
            / 1000,
            end_of_turn_timeout_secs=number(
                'end_of_turn_timeout_ms', d.end_of_turn_timeout_secs * 1000, 500, 10000
            )
            / 1000,
            transcript_turn_start=raw['transcript_turn_start']
            if isinstance(raw.get('transcript_turn_start'), bool)
            else d.transcript_turn_start,
            idle_timeout_secs=idle_timeout_ms / 1000,
            idle_max_check_ins=int(
                number('idle_max_check_ins', d.idle_max_check_ins, 0, 5)
            ),
            idle_fixed_goodbye=raw.get('idle_fixed_goodbye') is True,
            idle_goodbye_message=idle_goodbye.strip()
            if isinstance(idle_goodbye, str) and idle_goodbye.strip()
            else d.idle_goodbye_message,
        )

    def vad_params(self) -> VADParams:
        return VADParams(
            confidence=self.vad_confidence,
            start_secs=self.vad_start_secs,
            stop_secs=self.vad_stop_secs,
            min_volume=self.vad_min_volume,
        )

    def start_strategies(self) -> List[BaseUserTurnStartStrategy]:
        if not self.barge_in:
            return [
                VADWhenBotSilentStartStrategy(
                    discard_talk_over=True,
                    start_on_transcript=self.transcript_turn_start,
                )
            ]
        if self.barge_in_min_words == 0:
            # Plain VAD: any speech starts the turn, bot talking or not. A
            # transcript backs it up for speech VAD missed.
            strategies: List[BaseUserTurnStartStrategy] = [VADUserTurnStartStrategy()]
            if self.transcript_turn_start:
                strategies.append(TranscriptFallbackStartStrategy())
            return strategies
        return [
            VADWhenBotSilentStartStrategy(),
            MinWordsUserTurnStartStrategy(min_words=self.barge_in_min_words),
        ]

    def mute_strategies(self, *, will_greet: bool) -> List[BaseUserMuteStrategy]:
        """``will_greet``: the bot speaks first (a welcome message), so the user
        cannot end up muted waiting for speech that never comes."""
        # Always mute during in-flight tool calls so audio does not collide
        strategies: List[BaseUserMuteStrategy] = [FunctionCallUserMuteStrategy()]
        if self.mute_until_first_bot_complete and will_greet:
            strategies.insert(0, MuteUntilFirstBotCompleteUserMuteStrategy())
        return strategies

    def stop_strategies(self) -> List[BaseUserTurnStopStrategy]:
        return [
            TurnAnalyzerUserTurnStopStrategy(
                turn_analyzer=SharedSmartTurnAnalyzer(
                    params=SmartTurnParams(stop_secs=self.end_of_turn_timeout_secs)
                )
            )
        ]
