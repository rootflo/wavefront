"""Browser (WebRTC) app messages for a live voice session.

The browser talks to the running pipeline over Pipecat's RTVI data channel
(``PipelineTask`` enables RTVI by default):

Inbound (browser -> pipeline), via ``client.sendClientMessage(type, data)``:
    ``set_context``  {step, field?, language?, instruction?, allowedTools?}
        Swap the step overlay on the live system prompt, restrict the tools the
        LLM may call, and have the agent open the new step.
    ``interrupt``    {}  stop the bot's current speech (orb tap).
    ``switch_agent`` {agent_id}  hot-swap the voice agent in this live room. The
        target must be on the room's allowlist (enforced by the swap controller).
    ``app_event_ack`` {id, ok, error?, result?}  the app's answer to an ``app_event``.
        It becomes the result of the LLM tool call that raised the event.

Outbound (pipeline -> browser), via ``RTVIProcessor.send_server_message``:
    ``agent_state``  {state: listening | thinking | speaking}
    ``caption``      {role: 'agent', text, final}  what the bot is saying, as spoken
    ``transcript``   {role: 'user', text, final}   the user's finished utterance
    ``language_changed``     {language}  the agent settled on the user's language
    ``agent_switching``      {agent_id}  a swap started (show a pending state)
    ``agent_changed``        {agent_id, agent_name}  the swap finished
    ``agent_switch_failed``  {code, message}  the previous agent keeps running
    ``app_event``    {id, name, args, step}  an app tool (tool_type 'app') was called
        by the LLM; the app acts on it (navigate, save, ...) and replies with
        ``app_event_ack``. ``step`` is the step the call was made on, so the app can
        drop events from a page the customer already left.

One room is one pipeline: pages only send ``set_context`` / ``switch_agent``;
nothing here creates or restarts a conversation.

Language handling has two modes, chosen per room at creation
(``room_context_handles_language``):
    native (default)  the agent gets language rules and a ``detect_and_switch_language``
        tool; ``set_context.language`` also prefixes a language instruction.
    room context      only ``set_context.language`` changes the language (STT/TTS
        move with it); the prompt gets just the step overlay, and no
        ``language_changed`` event is emitted because no tool exists to raise it.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import (
    BotStoppedSpeakingFrame,
    Frame,
    InterruptionFrame,
    LLMMessagesAppendFrame,
    TTSTextFrame,
)
from pipecat.processors.aggregators.llm_context import NOT_GIVEN
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.string import (
    TextPartForConcatenation,
    concatenate_aggregated_text,
    match_endofsentence,
)

from call_processing.log.logger import logger
from call_processing.services.common.language_switch import queue_language_update
from call_processing.services.common.prompts import language_instruction
from call_processing.services.common.session_events import SessionEvents
from call_processing.services.webrtc.room_service import (
    ERR_INVALID_REQUEST,
    ERR_SWAP_FAILED,
)
from call_processing.services.webrtc.prompts import (
    STEP_OPENER,
    default_step_instruction,
    step_heading,
    step_language_line,
)

# Inbound message types
MSG_SET_CONTEXT = 'set_context'
MSG_INTERRUPT = 'interrupt'
MSG_SWITCH_AGENT = 'switch_agent'
MSG_APP_EVENT_ACK = 'app_event_ack'

# Outbound message types
MSG_AGENT_STATE = 'agent_state'
MSG_CAPTION = 'caption'
MSG_TRANSCRIPT = 'transcript'
MSG_LANGUAGE_CHANGED = 'language_changed'
MSG_AGENT_SWITCHING = 'agent_switching'
MSG_AGENT_CHANGED = 'agent_changed'
MSG_AGENT_SWITCH_FAILED = 'agent_switch_failed'
MSG_APP_EVENT = 'app_event'

OVERLAY_START = '<<APP_STEP_CONTEXT>>'
OVERLAY_END = '<<END_APP_STEP_CONTEXT>>'
_OVERLAY_RE = re.compile(
    re.escape(OVERLAY_START) + r'.*?' + re.escape(OVERLAY_END), re.S
)


# --------------------------------------------------------------------- parsing


@dataclass(frozen=True)
class SetContext:
    step: str
    field: Optional[str] = None
    language: Optional[str] = None
    instruction: Optional[str] = None
    # None = leave the tool set unchanged; empty = no agent tools for this step
    allowed_tools: Optional[Tuple[str, ...]] = None


def _clean_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_set_context(data: Any) -> Optional[SetContext]:
    """Validate a ``set_context`` payload. Returns None when it is unusable."""
    if not isinstance(data, dict):
        return None
    step = _clean_str(data.get('step'))
    if step is None:
        return None

    raw_tools = data.get('allowedTools', data.get('allowed_tools'))
    allowed: Optional[Tuple[str, ...]] = None
    if isinstance(raw_tools, (list, tuple)):
        allowed = tuple(t for t in raw_tools if isinstance(t, str))

    return SetContext(
        step=step,
        field=_clean_str(data.get('field')),
        language=_clean_str(data.get('language')),
        instruction=_clean_str(data.get('instruction')),
        allowed_tools=allowed,
    )


def parse_app_event_ack(data: Any) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Validate an ``app_event_ack`` payload.

    Returns ``(event_id, tool_result)`` where ``tool_result`` always has a boolean
    ``success``; None when the payload is unusable.
    """
    if not isinstance(data, dict):
        return None
    event_id = _clean_str(data.get('id'))
    if event_id is None:
        return None
    result = data.get('result')
    payload: Dict[str, Any] = dict(result) if isinstance(result, dict) else {}
    if data.get('ok') is True:
        payload['success'] = True
    else:
        payload['success'] = False
        payload.setdefault('error', _clean_str(data.get('error')) or 'rejected')
    return event_id, payload


# ------------------------------------------------------------- prompt / tools


def parse_switch_agent(data: Any) -> Optional[str]:
    """Validate a ``switch_agent`` payload. Returns the agent id, or None."""
    if not isinstance(data, dict):
        return None
    return _clean_str(data.get('agent_id', data.get('agentId')))


def build_step_overlay(ctx: SetContext) -> str:
    """The marked block appended to the system prompt for the current step."""
    where = f'{ctx.step}/{ctx.field}' if ctx.field else ctx.step
    lines = [step_heading(where)]
    if ctx.language:
        lines.append(step_language_line(ctx.language))
    lines.append(ctx.instruction or default_step_instruction(where))
    return f'{OVERLAY_START}\n' + '\n'.join(lines) + f'\n{OVERLAY_END}'


def strip_step_overlay(content: str) -> str:
    return _OVERLAY_RE.sub('', content).rstrip()


def apply_step_overlay(content: str, overlay: str) -> str:
    """Replace any previous step overlay in ``content`` with ``overlay``."""
    return f'{strip_step_overlay(content)}\n\n{overlay}'


def filter_function_schemas(
    schemas: Sequence[FunctionSchema],
    allowed: Optional[Sequence[str]],
    always_allowed: Sequence[str] = (),
) -> List[FunctionSchema]:
    """Subset of ``schemas`` the LLM may call.

    ``allowed=None`` keeps everything. ``always_allowed`` names (built-ins such
    as language switching) survive an empty allowlist.
    """
    if allowed is None:
        return list(schemas)
    permitted = set(allowed) | set(always_allowed)
    return [s for s in schemas if s.name in permitted]


# --------------------------------------------------------------------- captions


class CaptionAssembler:
    """Turns spoken-text frames into live subtitle updates.

    ``feed`` returns ``(text, final)`` after every frame: the current sentence
    so far (``final=False``), then the completed sentence (``final=True``). The
    next sentence starts fresh, so each caption replaces the previous one.
    """

    def __init__(self) -> None:
        self._parts: List[TextPartForConcatenation] = []

    def feed(
        self, text: str, includes_inter_frame_spaces: bool
    ) -> List[Tuple[str, bool]]:
        if not text:
            return []
        self._parts.append(TextPartForConcatenation(text, includes_inter_frame_spaces))
        joined = concatenate_aggregated_text(self._parts).strip()
        if not joined:
            return []

        updates: List[Tuple[str, bool]] = []
        while joined:
            end = match_endofsentence(joined)
            if not end:
                updates.append((joined, False))
                self._parts = [TextPartForConcatenation(joined, True)]
                return updates
            sentence, joined = joined[:end].strip(), joined[end:].strip()
            if sentence:
                updates.append((sentence, True))

        self._parts = []
        return updates

    def flush(self) -> Optional[Tuple[str, bool]]:
        """Complete whatever is buffered (bot stopped speaking)."""
        if not self._parts:
            return None
        text = concatenate_aggregated_text(self._parts).strip()
        self._parts = []
        return (text, True) if text else None

    def reset(self) -> None:
        self._parts = []


class BotCaptionProcessor(FrameProcessor):
    """Place after ``transport.output()``: emits captions as the bot speaks."""

    def __init__(self, messenger: 'ClientSessionMessenger', **kwargs):
        super().__init__(**kwargs)
        self._messenger = messenger
        self._assembler = CaptionAssembler()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, TTSTextFrame):
                for text, final in self._assembler.feed(
                    frame.text, frame.includes_inter_frame_spaces
                ):
                    await self._messenger.emit_caption(text, final)
            elif isinstance(frame, BotStoppedSpeakingFrame):
                flushed = self._assembler.flush()
                if flushed:
                    await self._messenger.emit_caption(*flushed)
            elif isinstance(frame, InterruptionFrame):
                self._assembler.reset()

        await self.push_frame(frame, direction)


# -------------------------------------------------------------------- messenger


class ClientSessionMessenger(SessionEvents):
    """Handles client (browser or app) messages for one live pipeline and emits UI events."""

    def __init__(
        self,
        *,
        context: Any,
        function_schemas: Sequence[FunctionSchema],
        language_state: Dict[str, Any],
        always_allowed_tools: Sequence[str] = (),
        supported_languages: Sequence[str] = (),
        tts_provider: str = '',
        stt_provider: str = '',
        tts_voice_ids: Optional[Dict[str, str]] = None,
        room_context_language: bool = False,
    ):
        # Room property (kept across agent swaps): the app alone drives the
        # language, so the prompt carries no language instruction prefix.
        self._room_context_language = room_context_language
        self._task: Any = None  # set via bind_task once the PipelineTask exists
        self._context = context
        self._function_schemas = list(function_schemas)
        self._language_state = language_state
        self._always_allowed = tuple(always_allowed_tools)
        self._supported_languages = list(supported_languages)
        self._tts_provider = tts_provider
        self._stt_provider = stt_provider
        self._tts_voice_ids = tts_voice_ids or {}
        self._last_context_key: Optional[tuple] = None
        self._last_context: Optional[SetContext] = None
        self._last_state: Optional[str] = None
        # Agent swap support
        self._on_switch_agent: Optional[Callable[[str], Awaitable[None]]] = None
        self._swapping = False
        self._deferred_context: Optional[SetContext] = None
        # App tool calls waiting for the browser's ack, keyed by event id
        self._pending_app_events: Dict[str, 'asyncio.Future[Dict[str, Any]]'] = {}

    def set_switch_handler(
        self, handler: Optional[Callable[[str], Awaitable[None]]]
    ) -> None:
        """``handler(agent_id)`` receives validated-shape ``switch_agent`` requests."""
        self._on_switch_agent = handler

    def bind_task(self, task: Any) -> None:
        """The messenger is needed to build the pipeline; the task comes after."""
        self._task = task

    # ------------------------------------------------------------- outbound

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self._task is None:
            return
        try:
            await self._task.rtvi.send_server_message(payload)
        except Exception as e:  # UI events must never break the call
            logger.warning(f"Failed to send '{payload.get('type')}' to browser: {e}")

    async def emit_agent_state(self, state: str) -> None:
        if state == self._last_state:
            return
        self._last_state = state
        await self._send({'type': MSG_AGENT_STATE, 'state': state})

    async def emit_caption(self, text: str, final: bool) -> None:
        await self._send(
            {'type': MSG_CAPTION, 'role': 'agent', 'text': text, 'final': final}
        )

    async def emit_transcript(self, text: str) -> None:
        if text and text.strip():
            await self._send(
                {'type': MSG_TRANSCRIPT, 'role': 'user', 'text': text, 'final': True}
            )

    async def emit_language_changed(self, language: str) -> None:
        await self._send({'type': MSG_LANGUAGE_CHANGED, 'language': language})

    async def emit_agent_switching(self, agent_id: str) -> None:
        await self._send({'type': MSG_AGENT_SWITCHING, 'agent_id': agent_id})

    async def emit_agent_changed(self, agent_id: str, agent_name: str) -> None:
        await self._send(
            {'type': MSG_AGENT_CHANGED, 'agent_id': agent_id, 'agent_name': agent_name}
        )

    async def emit_agent_switch_failed(self, code: str, message: str) -> None:
        await self._send(
            {'type': MSG_AGENT_SWITCH_FAILED, 'code': code, 'message': message}
        )

    async def emit_app_event(
        self, name: str, args: Dict[str, Any], timeout: float = 4.0
    ) -> Dict[str, Any]:
        """Raise an app tool call to the browser and wait for its ack.

        Returns the tool result for the LLM: ``{'success': True, ...}`` when the app
        accepted the event, otherwise ``{'success': False, 'error': ...}`` (rejected,
        timeout, no app attached, or the agent is being swapped).
        """
        if self._task is None:
            return {'success': False, 'error': 'no_app'}
        if self._swapping:
            return {'success': False, 'error': 'agent_swapping'}

        event_id = uuid.uuid4().hex
        future: 'asyncio.Future[Dict[str, Any]]' = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_app_events[event_id] = future
        step = self._last_context.step if self._last_context else None
        try:
            await self._send(
                {
                    'type': MSG_APP_EVENT,
                    'id': event_id,
                    'name': name,
                    'args': args or {},
                    'step': step,
                }
            )
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            logger.warning(f"App event '{name}' ({event_id}) was not acknowledged")
            return {'success': False, 'error': 'timeout'}
        finally:
            self._pending_app_events.pop(event_id, None)

    def resolve_app_event(self, event_id: str, result: Dict[str, Any]) -> bool:
        """Complete a pending app event. False when it is unknown or already done."""
        future = self._pending_app_events.get(event_id)
        if future is None or future.done():
            return False
        future.set_result(result)
        return True

    def fail_pending_app_events(self, error: str) -> None:
        """Fail every waiting app tool call (swap started, call ended)."""
        for future in list(self._pending_app_events.values()):
            if not future.done():
                future.set_result({'success': False, 'error': error})

    async def close(self) -> None:
        self.fail_pending_app_events('session_closed')

    # -------------------------------------------------------------- inbound

    async def handle_client_message(self, message: Any) -> None:
        """RTVI ``on_client_message`` handler (``message.type`` / ``message.data``)."""
        msg_type = getattr(message, 'type', None)
        data = getattr(message, 'data', None)
        if self._task is None:
            return
        try:
            if msg_type == MSG_SET_CONTEXT:
                ctx = parse_set_context(data)
                if ctx is None:
                    logger.warning(f'Ignoring invalid set_context payload: {data!r}')
                    return
                if self._swapping:
                    # The agent is being swapped: applying now would target the
                    # outgoing context. Keep only the latest and apply after.
                    self._deferred_context = ctx
                    return
                await self.apply_context(ctx)
            elif msg_type == MSG_INTERRUPT:
                await self.interrupt()
            elif msg_type == MSG_APP_EVENT_ACK:
                ack = parse_app_event_ack(data)
                if ack is None:
                    logger.warning(f'Ignoring invalid app_event_ack payload: {data!r}')
                    return
                if not self.resolve_app_event(*ack):
                    logger.info(f'app_event_ack {ack[0]} matched no pending event')
            elif msg_type == MSG_SWITCH_AGENT:
                agent_id = parse_switch_agent(data)
                if agent_id is None:
                    logger.warning(f'Ignoring invalid switch_agent payload: {data!r}')
                    await self.emit_agent_switch_failed(
                        ERR_INVALID_REQUEST, 'switch_agent needs an agent_id'
                    )
                    return
                if self._on_switch_agent is None:
                    await self.emit_agent_switch_failed(
                        ERR_SWAP_FAILED,
                        'Agent switching is not available in this session',
                    )
                    return
                await self._on_switch_agent(agent_id)
        except Exception as e:
            logger.error(
                f'Error handling browser message {msg_type}: {e}', exc_info=True
            )

    async def interrupt(self) -> None:
        await self._task.rtvi.interrupt_bot()

    # -------------------------------------------------------------- agent swap

    def rebind(
        self,
        *,
        context: Any,
        function_schemas: Sequence[FunctionSchema],
        language_state: Dict[str, Any],
        supported_languages: Sequence[str] = (),
        tts_provider: str = '',
        stt_provider: str = '',
        tts_voice_ids: Optional[Dict[str, str]] = None,
    ) -> None:
        """Point the messenger at a new agent's context and language state."""
        self._context = context
        self._function_schemas = list(function_schemas)
        self._language_state = language_state
        self._supported_languages = list(supported_languages)
        self._tts_provider = tts_provider
        self._stt_provider = stt_provider
        self._tts_voice_ids = tts_voice_ids or {}
        # The new context has no overlay yet: let the same step apply again
        self._last_context_key = None
        self._last_state = None

    def begin_swap(self) -> None:
        self._swapping = True
        # The outgoing agent's tool calls can no longer be answered into its context
        self.fail_pending_app_events('agent_swapping')

    def will_reopen_step(self) -> bool:
        """True when ``finish_swap`` will apply a step context (and so speak)."""
        return self._deferred_context is not None or self._last_context is not None

    async def finish_swap(self) -> None:
        """End the swap window and re-apply the app step on the (new) context.

        Uses the ``set_context`` that arrived mid-swap if any, else the last one
        applied, so the new agent keeps working on the same app step.
        """
        self._swapping = False
        pending = self._deferred_context or self._last_context
        self._deferred_context = None
        if pending is not None:
            await self.apply_context(pending)

    async def apply_context(self, ctx: SetContext) -> None:
        key = (ctx.step, ctx.field, ctx.language, ctx.instruction, ctx.allowed_tools)
        if key == self._last_context_key:
            return  # duplicate (e.g. effect re-run); nothing to change
        first = self._last_context_key is None
        self._last_context_key = key
        self._last_context = ctx

        overlay = build_step_overlay(ctx)
        await self._apply_prompt(ctx, overlay)
        self._apply_tools(ctx)
        logger.info(
            f'Browser set_context step={ctx.step} field={ctx.field} '
            f'language={ctx.language} tools={ctx.allowed_tools}'
        )

        # The first context lets the welcome message finish; later ones cut the
        # previous step's speech off before the agent opens the new step.
        if not first:
            await self.interrupt()
        await self._task.queue_frame(
            LLMMessagesAppendFrame(
                messages=[{'role': 'user', 'content': STEP_OPENER}], run_llm=True
            )
        )

    async def _apply_prompt(self, ctx: SetContext, overlay: str) -> None:
        messages = list(self._context.get_messages())
        original = self._language_state.get('original_system_prompt')

        if original:
            # Multi-language agent: the language tool rebuilds the system prompt
            # from ``original_system_prompt``, so the overlay must live there too.
            new_original = apply_step_overlay(original, overlay)
            self._language_state['original_system_prompt'] = new_original
            language = self._resolve_language(ctx.language)
            if self._room_context_language:
                # The overlay already states the language; no extra instruction
                content = new_original
            else:
                content = f'{language_instruction(language)}\n\n{new_original}'
            await self._switch_services_language(language)
        else:
            current = ''
            if messages and messages[0].get('role') == 'system':
                existing = messages[0].get('content')
                current = existing if isinstance(existing, str) else ''
            content = apply_step_overlay(current, overlay)

        system_message = {'role': 'system', 'content': content}
        if messages and messages[0].get('role') == 'system':
            messages[0] = system_message
        else:
            messages.insert(0, system_message)
        self._context.set_messages(messages)

    def _resolve_language(self, requested: Optional[str]) -> str:
        current = self._language_state.get('current_language', 'en')
        if requested and requested in self._supported_languages:
            return requested
        return current

    async def _switch_services_language(self, language: str) -> None:
        """Move TTS/STT to ``language`` (multi-language agents only)."""
        current = self._language_state.get('current_language')
        if language == current:
            return
        await queue_language_update(
            self._task,
            tts_provider=self._tts_provider,
            stt_provider=self._stt_provider,
            tts_voice_ids=self._tts_voice_ids,
            language=language,
        )
        self._language_state['current_language'] = language
        self._language_state['switch_count'] = (
            self._language_state.get('switch_count', 0) + 1
        )

    def _apply_tools(self, ctx: SetContext) -> None:
        if ctx.allowed_tools is None:
            return
        subset = filter_function_schemas(
            self._function_schemas, ctx.allowed_tools, self._always_allowed
        )
        # An empty tools list is rejected by some LLM APIs; NOT_GIVEN disables tools
        self._context.set_tools(
            ToolsSchema(standard_tools=subset) if subset else NOT_GIVEN
        )
