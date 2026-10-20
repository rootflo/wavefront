"""Per-agent pipeline pieces, kept apart from the per-call (shared) state.

A browser (WebRTC) room can swap its voice agent mid-session. Everything that
belongs to *one* agent (STT, LLM, TTS, system prompt, tools, conversation
context and its aggregators, language state) lives in an ``AgentStack`` so a
whole stack can be built off to the side and replaced while the transport, the
``PipelineTask`` and the peer connection keep running.

Everything that belongs to the *call* (stats, transcript, the task handle, the
browser messenger) lives in ``SharedSession`` and outlives any single stack.
Both the telephony and the browser flow build their agent through this split;
only browser rooms ever swap it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pipecat.adapters.schemas.function_schema import FunctionSchema

from call_processing.services.common.session_events import SessionEvents

_NO_EVENTS = SessionEvents()


@dataclass
class AgentStack:
    agent_config: Dict[str, Any]
    stt: Any
    llm: Any
    tts: Any
    context: Any
    context_aggregator: Any
    language_state: Dict[str, Any]
    # Every schema the LLM may be given; includes ``detect_and_switch_language``
    # unless the room's context drives the language (room_context_handles_language)
    function_schemas: List[FunctionSchema]
    # Empty for single-language agents
    supported_languages: List[str]
    tts_provider: str
    stt_provider: str
    tts_voice_ids: Dict[str, str]
    welcome_message: str
    # Between LLM and TTS: speaks thinking / tool-call fillers
    filler: Any

    @property
    def agent_id(self) -> str:
        agent_id = self.agent_config.get('id')
        return str(agent_id) if agent_id else ''

    @property
    def agent_name(self) -> str:
        return str(self.agent_config.get('name') or '')

    @property
    def slot_a_processors(self) -> List[Any]:
        """Everything between ``transport.input()`` and ``transport.output()``."""
        return [
            self.stt,
            self.context_aggregator.user(),
            self.llm,
            self.filler,
            self.tts,
        ]

    @property
    def slot_b_processors(self) -> List[Any]:
        """Everything after ``transport.output()``."""
        return [self.context_aggregator.assistant()]


@dataclass
class SharedSession:
    """State shared by every agent stack of one call."""

    call_stats: Dict[str, Any]
    transcript_log: List[Dict[str, Any]]
    # {'task': PipelineTask}; filled once the task exists
    task_container: Dict[str, Any] = field(default_factory=lambda: {'task': None})
    # ClientSessionMessenger for browser sessions, else None
    messenger: Optional[Any] = None
    # The stack currently serving the call (updated by every agent swap)
    active_stack: Optional[AgentStack] = None

    @property
    def events(self) -> SessionEvents:
        """Where conversation events go: the browser messenger, else nowhere."""
        return self.messenger or _NO_EVENTS
