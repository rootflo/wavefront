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
        "end_of_turn_timeout_ms": 3000  // silence that ends a turn Smart Turn
                                        // still thinks is unfinished
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

Noisy phone lines want a higher confidence / volume floor and more barge-in
words; a quiet browser can go lower for snappier interruptions. Every reply
waits at least ``vad_stop_ms``, so raise it only if the bot keeps answering
before the user has finished.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Mapping

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
    VADUserTurnStartStrategy,
)
from pipecat.turns.user_stop import (
    BaseUserTurnStopStrategy,
    TurnAnalyzerUserTurnStopStrategy,
)

from call_processing.services.conversation_config import (
    bounded_number,
    config_section,
)
from call_processing.services.smart_turn import SharedSmartTurnAnalyzer

_SECTION = 'conversation_config.turn_taking'


class VADWhenBotSilentStartStrategy(VADUserTurnStartStrategy):
    """VAD starts the user's turn only while the bot is silent.

    Pipecat stops at the first start strategy that fires, so a plain VAD
    strategy listed before ``MinWordsUserTurnStartStrategy`` would always win
    and any noise would cut the bot off. While the bot speaks this defers to
    MinWords; while it is silent, VAD keeps turn starts instant.

    ``discard_talk_over``: no MinWords strategy follows (barge-in is off), so
    what the user says over the bot is thrown away instead of piling up into
    their next turn. If they are still speaking when the bot finishes, their
    turn starts then rather than waiting for the next pause.
    """

    def __init__(self, *, discard_talk_over: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._discard_talk_over = discard_talk_over
        self._bot_speaking = False
        self._talking_over = False

    async def process_frame(self, frame: Frame) -> ProcessFrameResult:
        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            if self._discard_talk_over and self._talking_over:
                self._talking_over = False
                await self.trigger_user_turn_started()
                return ProcessFrameResult.STOP
        if self._bot_speaking:
            if self._discard_talk_over:
                if isinstance(frame, VADUserStartedSpeakingFrame):
                    self._talking_over = True
                elif isinstance(frame, VADUserStoppedSpeakingFrame):
                    self._talking_over = False
                elif isinstance(frame, (TranscriptionFrame, InterimTranscriptionFrame)):
                    await self.trigger_reset_aggregation()
            return ProcessFrameResult.CONTINUE
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

    @classmethod
    def from_agent_config(cls, agent_config: Mapping[str, Any]) -> TurnTakingConfig:
        raw = config_section(agent_config, 'turn_taking')
        d = cls()

        def number(key, default, minimum, maximum):
            return bounded_number(
                raw, key, default, minimum=minimum, maximum=maximum, path=_SECTION
            )

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
            return [VADWhenBotSilentStartStrategy(discard_talk_over=True)]
        if self.barge_in_min_words == 0:
            # Plain VAD: any speech starts the turn, bot talking or not
            return [VADUserTurnStartStrategy()]
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
