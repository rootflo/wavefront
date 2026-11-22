"""Filler speech ("Hmm", "One moment") pushed straight into TTS.

Sits between the LLM and TTS. Fillers enter here instead of at the top of the
pipeline, so they skip STT, the user aggregator and a busy LLM and are heard
right away.

The thinking filler is latency-gated: it is armed when the user's turn ends and
only spoken if the LLM has not started answering within ``delay_secs``. A fast
reply goes out with no filler in front of it; a slow one gets a short
backchannel instead of dead air.

Per agent, via ``conversation_config.filler_speech`` on the voice agent::

    {
      "filler_speech": {
        "thinking": true,               // backchannel while the LLM is slow
        "thinking_delay_ms": 800,       // how long a silence is tolerated first
        "thinking_phrases": {"en": ["Hmm", "Okay"]},   // optional override
        "before_tool_call": true,       // "One moment" before a tool runs
        "tool_call_phrases": {"en": ["One sec"]}       // optional override
      }
    }

Missing keys fall back to the defaults below and the built-in phrases.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

from pipecat.frames.frames import (
    Frame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    LLMFullResponseStartFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from call_processing.constants.filler_phrases import FILLER_PHRASES, THINKING_PHRASES
from call_processing.services.common.conversation_config import (
    bounded_number,
    config_section,
)

# Below this the silence before a reply sounds natural; above it, it reads as lag.
THINKING_FILLER_DELAY_SECS = 0.8
_MAX_THINKING_DELAY_SECS = 5.0
# Defaults for agents whose conversation_config does not set these
DEFAULT_THINKING = False
DEFAULT_BEFORE_TOOL_CALL = False

PhraseBook = Mapping[str, Sequence[str]]


@dataclass(frozen=True)
class FillerSpeechConfig:
    thinking: bool
    thinking_delay_secs: float
    thinking_phrases: PhraseBook
    before_tool_call: bool
    tool_call_phrases: PhraseBook

    def thinking_phrases_for(self, language: str) -> List[str]:
        return _phrases_for(self.thinking_phrases, THINKING_PHRASES, language)

    def tool_call_phrases_for(self, language: str) -> List[str]:
        return _phrases_for(self.tool_call_phrases, FILLER_PHRASES, language)

    @classmethod
    def from_agent_config(cls, agent_config: Mapping[str, Any]) -> FillerSpeechConfig:
        raw = config_section(agent_config, 'filler_speech')
        delay_ms = bounded_number(
            raw,
            'thinking_delay_ms',
            THINKING_FILLER_DELAY_SECS * 1000,
            minimum=0,
            maximum=_MAX_THINKING_DELAY_SECS * 1000,
            path='conversation_config.filler_speech',
        )

        return cls(
            thinking=bool(raw.get('thinking', DEFAULT_THINKING)),
            thinking_delay_secs=delay_ms / 1000,
            thinking_phrases=_phrase_book(raw.get('thinking_phrases')),
            before_tool_call=bool(
                raw.get('before_tool_call', DEFAULT_BEFORE_TOOL_CALL)
            ),
            tool_call_phrases=_phrase_book(raw.get('tool_call_phrases')),
        )


def _phrase_book(value: Any) -> Dict[str, List[str]]:
    """``{language: [phrase, ...]}`` with blank and non-string entries dropped."""
    if not isinstance(value, dict):
        return {}
    book = {}
    for language, phrases in value.items():
        if isinstance(phrases, str):
            phrases = [phrases]
        if isinstance(phrases, list):
            cleaned = [p.strip() for p in phrases if isinstance(p, str) and p.strip()]
            if cleaned:
                book[str(language)] = cleaned
    return book


def _phrases_for(custom: PhraseBook, builtin: PhraseBook, language: str) -> List[str]:
    # The call's language first (custom, then built-in); English only as a last resort
    for lang in (language, 'en'):
        for book in (custom, builtin):
            if book.get(lang):
                return list(book[lang])
    return []


# Frames that mean the thinking filler is no longer wanted
_CANCEL_FRAMES = (
    LLMFullResponseStartFrame,
    FunctionCallsStartedFrame,
    InterruptionFrame,
    UserStartedSpeakingFrame,
)


class FillerSpeechProcessor(FrameProcessor):
    def __init__(self, *, delay_secs: float = THINKING_FILLER_DELAY_SECS, **kwargs):
        super().__init__(**kwargs)
        self._delay_secs = delay_secs
        self._pending: Optional[asyncio.Task] = None
        self._last_phrase: Optional[str] = None

    def _pick(self, phrases: Sequence[str]) -> str:
        # Never the same backchannel twice in a row
        choices = [p for p in phrases if p != self._last_phrase] or list(phrases)
        self._last_phrase = random.choice(choices)
        return self._last_phrase

    async def arm_thinking_filler(
        self, phrases: Union[Sequence[str], Callable[[], Sequence[str]]]
    ) -> None:
        """Speak one of ``phrases`` unless the LLM starts answering first.

        A callable is read when the filler fires, so the phrase follows a
        language switch made after arming (``direct_language_switch.py``).
        """
        await self.cancel_thinking_filler()
        if phrases:
            self._pending = self.create_task(self._speak_later(phrases))

    async def cancel_thinking_filler(self) -> None:
        if self._pending:
            await self.cancel_task(self._pending)
            self._pending = None

    async def speak_one_of(self, phrases: Sequence[str]) -> None:
        if phrases:
            await self.push_frame(
                TTSSpeakFrame(self._pick(phrases), append_to_context=False)
            )

    async def _speak_later(
        self, phrases: Union[Sequence[str], Callable[[], Sequence[str]]]
    ) -> None:
        await asyncio.sleep(self._delay_secs)
        self._pending = None
        choices = phrases() if callable(phrases) else phrases
        if choices:
            await self.push_frame(
                TTSSpeakFrame(self._pick(choices), append_to_context=False)
            )

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, _CANCEL_FRAMES):
            await self.cancel_thinking_filler()
        await self.push_frame(frame, direction)

    async def cleanup(self):
        await super().cleanup()
        await self.cancel_thinking_filler()
