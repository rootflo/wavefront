"""Hot-swap the voice agent of a live browser (WebRTC) room.

Why this is not "restart ``run_conversation``": the SmallWebRTC input/output
transports disconnect the peer connection when they stop or are cancelled, so
ending the ``PipelineWorker`` would drop the browser. The swap therefore happens
*inside* the running pipeline. The transport, the ``PipelineWorker``, RTVI, VAD,
the idle watchdog and the room session timers are never touched:

    transport.input -> Slot STT -> Slot A -> Slot TTS -> transport.output
                                          -> BotCaptionProcessor -> Slot B

Slot A hosts the agent's user aggregator -> LLM -> fillers, slot B its
assistant aggregator (which must stay after ``transport.output()``). STT and TTS
have slots of their own: when the new agent's STT (or TTS) config is identical
to the live one, that slot is left alone and its websocket stays connected.
Each slot wraps its processors in an inner ``Pipeline`` that can be replaced.

Swap order (``AgentSwapController``): build the new stack off to the side
(a failure leaves the old agent untouched), start the new inner pipelines,
commit the swapped slots in one synchronous step (no frame can fall between the
old and the new stack), cut the old agent's speech, stop the old pipelines
(closing any replaced STT/TTS websockets) and let the new agent introduce itself
with the carried conversation history (rooms created with
``carry_history_on_swap=False`` start the new agent with a clean context
instead).
"""

from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
)
from uuid import UUID

from pipecat.frames.frames import (
    CancelFrame,
    ErrorFrame,
    Frame,
    InputAudioRawFrame,
    LLMMessagesAppendFrame,
    StartFrame,
)
from pipecat.pipeline.pipeline import Pipeline, PipelineSink, PipelineSource
from pipecat.processors.frame_processor import (
    FrameDirection,
    FrameProcessor,
    FrameProcessorSetup,
)

from call_processing.log.logger import logger
from call_processing.services.common.agent_stack import AgentStack, SharedSession
from call_processing.services.webrtc.app_messages import strip_step_overlay
from call_processing.services.webrtc.prompts import build_handoff_note, is_step_opener
from call_processing.services.webrtc.room_service import (
    ERR_AGENT_NOT_ALLOWED,
    ERR_AGENT_UNAVAILABLE,
    ERR_ALREADY_ACTIVE,
    ERR_SWAP_FAILED,
    ERR_SWAP_IN_PROGRESS,
    ERR_SWAP_LIMIT_REACHED,
)

DEFAULT_MAX_SWAPS = 10
DEFAULT_COOLDOWN_SECS = 2.0
DEFAULT_SWAP_TIMEOUT_SECS = 15.0
# How long to wait for the old stack to acknowledge its CancelFrame
_RETIRE_TIMEOUT_SECS = 3.0

_ERROR_MESSAGES = {
    ERR_AGENT_NOT_ALLOWED: 'This agent is not available in this room',
    ERR_AGENT_UNAVAILABLE: 'That agent is not available right now',
    ERR_SWAP_IN_PROGRESS: 'An agent switch is already in progress, try again shortly',
    ERR_SWAP_LIMIT_REACHED: 'The agent switch limit for this session was reached',
    ERR_ALREADY_ACTIVE: 'That agent is already active',
    ERR_SWAP_FAILED: 'Could not switch agents, the previous agent is still active',
}


class SwapError(Exception):
    """A swap failed with a stable error ``code`` (see ``webrtc_room_service``)."""

    def __init__(self, code: str, detail: str = ''):
        super().__init__(detail or _ERROR_MESSAGES.get(code, code))
        self.code = code


# ------------------------------------------------------------------- the slot


class _Inner:
    """One generation of a slot's processors, wrapped in its own Pipeline."""

    def __init__(self) -> None:
        self.pipeline: Optional[Pipeline] = None
        self.start_id: Optional[int] = None
        self.started = asyncio.Event()
        self.cancel_id: Optional[int] = None
        self.cancelled = asyncio.Event()
        self.error: Optional[ErrorFrame] = None


class SwappableSlot(FrameProcessor):
    """Hosts a replaceable group of processors inside a running pipeline.

    Frames are forwarded into the current inner pipeline, and whatever leaves it
    is pushed on from the slot, so to its neighbours the slot looks like the
    processors themselves. ``prepare`` builds and starts a replacement off to the
    side, ``commit`` switches to it atomically and ``retire`` stops the old one.

    The replacement receives a copy of the ``StartFrame`` the slot saw, and its
    own start/cancel acknowledgements are swallowed so they never reach the
    transport (which would restart or cancel it).
    """

    def __init__(
        self, processors: Sequence[FrameProcessor], *, name: Optional[str] = None
    ):
        super().__init__(name=name)
        self._setup_params: Optional[FrameProcessorSetup] = None
        self._start_frame: Optional[StartFrame] = None
        self._gate_audio = False
        self._pending: List[_Inner] = []
        self._current = self._make_inner(processors)

    # ---- inner pipeline wiring

    def _make_inner(self, processors: Sequence[FrameProcessor]) -> _Inner:
        inner = _Inner()

        async def up(frame: Frame, direction: FrameDirection) -> None:
            await self._inner_up(inner, frame)

        async def down(frame: Frame, direction: FrameDirection) -> None:
            await self._inner_down(inner, frame)

        inner.pipeline = Pipeline(
            list(processors),
            source=PipelineSource(up, name=f'{self}::Source'),
            sink=PipelineSink(down, name=f'{self}::Sink'),
        )
        return inner

    async def _inner_up(self, inner: _Inner, frame: Frame) -> None:
        if inner is self._current:
            await self.push_frame(frame, FrameDirection.UPSTREAM)
        elif isinstance(frame, ErrorFrame) and inner.error is None:
            # A replacement failing to come up: report to the swap, not the call
            inner.error = frame

    async def _inner_down(self, inner: _Inner, frame: Frame) -> None:
        if (
            inner.start_id is not None
            and isinstance(frame, StartFrame)
            and frame.id == inner.start_id
        ):
            inner.started.set()
            return
        if inner is not self._current:
            if inner.cancel_id is not None and frame.id == inner.cancel_id:
                inner.cancelled.set()
            return
        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    # ---- compound-processor surface (metrics, introspection)

    @property
    def processors(self) -> List[FrameProcessor]:
        return [self._current.pipeline]

    @property
    def entry_processors(self) -> List[FrameProcessor]:
        return [self._current.pipeline]

    def processors_with_metrics(self) -> List[FrameProcessor]:
        return self._current.pipeline.processors_with_metrics()

    # ---- FrameProcessor lifecycle

    async def setup(self, setup: FrameProcessorSetup):
        await super().setup(setup)
        self._setup_params = setup
        await self._current.pipeline.setup(setup)

    async def cleanup(self):
        await super().cleanup()
        for inner in [self._current, *self._pending]:
            await inner.pipeline.cleanup()
        self._pending.clear()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            self._start_frame = frame
        if (
            self._gate_audio
            and direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, InputAudioRawFrame)
        ):
            return  # A swap is in progress: the outgoing agent hears nothing new

        await self._current.pipeline.queue_frame(frame, direction)

    # ---- swapping

    def gate_audio(self, gated: bool) -> None:
        """Stop (or resume) forwarding the user's audio into the current stack."""
        self._gate_audio = gated

    async def prepare(
        self, processors: Sequence[FrameProcessor], timeout: float = 10.0
    ) -> _Inner:
        """Build and start a replacement stack. The current one keeps running."""
        if self._setup_params is None or self._start_frame is None:
            raise RuntimeError(f'{self} has not been started')

        inner = self._make_inner(processors)
        self._pending.append(inner)
        try:
            await inner.pipeline.setup(self._setup_params)
            start = copy.copy(self._start_frame)  # same id: recognised at our sink
            inner.start_id = start.id
            await inner.pipeline.queue_frame(start, FrameDirection.DOWNSTREAM)
            await asyncio.wait_for(inner.started.wait(), timeout)
            if inner.error is not None:
                raise RuntimeError(f'new stack failed to start: {inner.error.error}')
        except BaseException:
            await self.retire(inner)
            raise
        return inner

    def commit(self, inner: _Inner) -> _Inner:
        """Make ``inner`` the live stack (synchronous). Returns the one it replaced."""
        old = self._current
        self._current = inner
        if inner in self._pending:
            self._pending.remove(inner)
        return old

    async def retire(self, inner: _Inner) -> None:
        """Stop a stack that is not live (or never went live) and clean it up."""
        if inner in self._pending:
            self._pending.remove(inner)
        if inner is self._current:
            return
        try:
            cancel = CancelFrame(reason='agent swap')
            inner.cancel_id = cancel.id
            await inner.pipeline.queue_frame(cancel, FrameDirection.DOWNSTREAM)
            await asyncio.wait_for(inner.cancelled.wait(), _RETIRE_TIMEOUT_SECS)
        except asyncio.TimeoutError:
            logger.warning(f'{self}: old stack did not acknowledge cancel in time')
        except Exception as e:
            logger.warning(f'{self}: error cancelling old stack: {e}')
        finally:
            try:
                await inner.pipeline.cleanup()
            except Exception as e:
                logger.warning(f'{self}: error cleaning up old stack: {e}')


# --------------------------------------------------------- conversation history


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get('text', '')
            for part in content
            if isinstance(part, dict) and part.get('type') == 'text'
        ]
        return ' '.join(p for p in parts if p)
    return ''


def build_handoff_history(messages: Sequence[Any]) -> List[Dict[str, str]]:
    """User/assistant text turns of a conversation, ready for a new agent.

    Drops the system prompt (the new agent has its own), the app-step overlay and
    opener, and tool calls / results: those are provider-specific and may not
    mean anything to the new agent's LLM.
    """
    history: List[Dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue  # provider-specific message objects
        role = message.get('role')
        if role not in ('user', 'assistant'):
            continue
        if message.get('tool_calls') or message.get('function_call'):
            continue
        text = strip_step_overlay(_message_text(message.get('content'))).strip()
        if not text or is_step_opener(text):
            continue
        history.append({'role': role, 'content': text})
    return history


# ------------------------------------------------------------------ controller


def _service_change_reason(
    new_config: Dict[str, Any], old_config: Dict[str, Any]
) -> Optional[str]:
    """Why a live STT/TTS cannot serve ``new_config`` (None if it can).

    Names the differing keys only: the configs hold credentials.
    """
    if not new_config or not old_config:
        return 'no config to compare'
    if new_config == old_config:
        return None
    keys = sorted(
        k
        for k in new_config.keys() | old_config.keys()
        if k != 'parameters' and new_config.get(k) != old_config.get(k)
    )
    new_params = new_config.get('parameters') or {}
    old_params = old_config.get('parameters') or {}
    keys += sorted(
        f'parameters.{k}'
        for k in new_params.keys() | old_params.keys()
        if new_params.get(k) != old_params.get(k)
    )
    return f'config differs in {", ".join(keys)}'


@dataclass
class SwapOptions:
    """Policy and collaborators for hot-swapping, provided by the session."""

    # Agents the browser may switch to (from the room record, set by floware)
    allowed_agent_ids: Set[str]
    # ``VoiceAgentCacheService.get_all_agent_configs``
    load_agent_configs: Callable[[UUID], Awaitable[Dict[str, Any]]]
    # Called after a successful swap, e.g. to update the room record
    on_agent_switched: Optional[Callable[[str], Any]] = None
    max_swaps: int = DEFAULT_MAX_SWAPS
    cooldown_secs: float = DEFAULT_COOLDOWN_SECS
    timeout_secs: float = DEFAULT_SWAP_TIMEOUT_SECS
    # False: the new agent starts with only its own system prompt (set per room)
    carry_history: bool = True
    # Pre-warmed configs keyed by agent id (filled at room join). Mutated in place.
    config_cache: Optional[Dict[str, Dict[str, Any]]] = None


@dataclass
class SessionHooks:
    """Optional hooks for ``WebRTCConversation`` (browser sessions)."""

    swap: Optional[SwapOptions] = None
    # Called once the pipeline task exists, with the controller (None if swapping
    # is not enabled). Lets the session service hold a handle to the live call.
    on_ready: Optional[Callable[[Optional['AgentSwapController']], None]] = None


class AgentSwapController:
    def __init__(
        self,
        *,
        slot_stt: SwappableSlot,
        slot_a: SwappableSlot,
        slot_tts: SwappableSlot,
        slot_b: SwappableSlot,
        task: Any,
        messenger: Any,
        shared: SharedSession,
        build_stack: Callable[[Dict[str, Any]], AgentStack],
        stack: AgentStack,
        options: SwapOptions,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._slot_stt = slot_stt
        self._slot_a = slot_a
        self._slot_tts = slot_tts
        self._slot_b = slot_b
        self._task = task
        self._messenger = messenger
        self._shared = shared
        self._build_stack = build_stack
        self._stack = stack
        self._options = options
        self._clock = clock

        self._swapping = False
        self._swap_count = 0
        self._last_swap_end: Optional[float] = None
        self._swap_task: Optional[asyncio.Task] = None
        self._closed = False

    # ---- introspection

    @property
    def current_agent_id(self) -> str:
        return self._stack.agent_id

    @property
    def swap_count(self) -> int:
        return self._swap_count

    @property
    def swapping(self) -> bool:
        return self._swapping

    # ---- requests

    def _precheck(self, agent_id: str) -> Optional[str]:
        """Synchronous admission check. Returns an error code or None."""
        if self._closed:
            return ERR_SWAP_FAILED
        try:
            agent_id = str(UUID(agent_id))
        except ValueError:
            return ERR_AGENT_NOT_ALLOWED
        if agent_id not in self._options.allowed_agent_ids:
            return ERR_AGENT_NOT_ALLOWED
        if self._swapping:
            return ERR_SWAP_IN_PROGRESS
        if agent_id == self.current_agent_id:
            return ERR_ALREADY_ACTIVE
        if self._swap_count >= self._options.max_swaps:
            return ERR_SWAP_LIMIT_REACHED
        if (
            self._last_swap_end is not None
            and self._clock() - self._last_swap_end < self._options.cooldown_secs
        ):
            return ERR_SWAP_IN_PROGRESS
        return None

    async def request_switch(self, agent_id: str) -> None:
        """Entry point for the browser's ``switch_agent`` message.

        Admission is decided synchronously (so two quick requests cannot both
        start); the swap itself runs in the background and reports through the
        messenger (``agent_switching`` / ``agent_changed`` / ``agent_switch_failed``).
        """
        code = self._precheck(agent_id)
        if code:
            await self._messenger.emit_agent_switch_failed(code, _ERROR_MESSAGES[code])
            return

        agent_id = str(UUID(agent_id))
        self._swapping = True
        self._messenger.begin_swap()
        self._swap_task = asyncio.create_task(
            self._run_swap(agent_id), name=f'agent-swap-{agent_id}'
        )

    async def close(self) -> None:
        """Cancel an in-flight swap (disconnect / max duration / shutdown)."""
        self._closed = True
        task = self._swap_task
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    # ---- the swap

    async def _run_swap(self, agent_id: str) -> None:
        try:
            await self._messenger.emit_agent_switching(agent_id)
            await self._swap(agent_id)
        except asyncio.CancelledError:
            logger.info(f'Agent swap to {agent_id} cancelled')
            raise
        except asyncio.TimeoutError:
            logger.error(f'Agent swap to {agent_id} timed out')
            await self._fail(ERR_SWAP_FAILED)
        except SwapError as e:
            logger.warning(f'Agent swap to {agent_id} failed: {e.code}: {e}')
            await self._fail(e.code)
        except Exception as e:
            logger.error(f'Agent swap to {agent_id} failed: {e}', exc_info=True)
            await self._fail(ERR_SWAP_FAILED)
        finally:
            self._slot_stt.gate_audio(False)
            self._swapping = False
            self._last_swap_end = self._clock()
            if not self._closed:
                # Close the swap window: a failed swap keeps the old agent and
                # applies any set_context that arrived meanwhile to it.
                try:
                    await self._messenger.finish_swap()
                except Exception as e:
                    logger.warning(f'Error finishing agent swap: {e}')

    async def _fail(self, code: str) -> None:
        await self._messenger.emit_agent_switch_failed(code, _ERROR_MESSAGES[code])

    async def _swap(self, agent_id: str) -> None:
        old_stack = self._stack
        # The timeout covers everything up to the commit. After it the swap is
        # irreversible and runs to completion.
        new_stack, prepared = await asyncio.wait_for(
            self._build_and_prepare(agent_id), self._options.timeout_secs
        )

        # 3. Commit. From here on there is no way back, and nothing awaits
        #    between swapping the slots, so no frame sees a half-swap.
        try:
            if self._options.carry_history:
                self._seed_context(new_stack, old_stack)
            replaced = [(slot, slot.commit(inner)) for slot, inner in prepared]
        except BaseException:
            await self._retire_all(prepared)
            raise
        self._slot_stt.gate_audio(False)
        self._stack = new_stack
        self._shared.active_stack = new_stack
        self._swap_count += 1
        self._shared.call_stats['agent_switch_count'] = self._swap_count
        self._shared.call_stats['_prior_language_switches'] = (
            self._shared.call_stats.get('_prior_language_switches', 0)
            + old_stack.language_state.get('switch_count', 0)
        )

        # 4. Cut the old agent's speech and stop its stack (closes STT/TTS sockets).
        await asyncio.shield(self._finish_commit(old_stack, new_stack, replaced))

    async def _load_configs(self, agent_id: str) -> Dict[str, Any]:
        cache = self._options.config_cache
        if cache is not None and agent_id in cache:
            return cache[agent_id]
        configs = await self._options.load_agent_configs(UUID(agent_id))
        if cache is not None and configs:
            cache[agent_id] = configs
        return configs

    async def _build_and_prepare(self, agent_id: str):
        # 1. Build the new stack off to the side. Nothing live is touched yet.
        try:
            configs = await self._load_configs(agent_id)
        except Exception as e:
            logger.warning(f'Could not load agent {agent_id} for swap: {e}')
            raise SwapError(ERR_AGENT_UNAVAILABLE)
        agent = (configs or {}).get('agent') or {}
        if agent.get('status', 'active') != 'active':
            raise SwapError(ERR_AGENT_UNAVAILABLE)
        try:
            new_stack = self._build_stack(self._carry_language(configs))
        except Exception as e:
            logger.error(
                f'Could not build agent {agent_id} for swap: {e}', exc_info=True
            )
            raise SwapError(ERR_SWAP_FAILED)

        # 2. Start the new stack in its slots while the old one still serves.
        #    The user's audio is gated so the old agent starts no new turn.
        self._slot_stt.gate_audio(True)
        prepared = await self._prepare_all(self._slots_to_swap(new_stack))

        return new_stack, prepared

    def _carry_language(self, configs: Dict[str, Any]) -> Dict[str, Any]:
        """Start the new agent in the language the conversation is in.

        When the live language (picked by the user, the app or the language
        tool) is one the new agent supports, it becomes the new agent's default
        for this call: its prompt, STT and TTS start there, so the caller is not
        switched back to another language, and STT/TTS built for the same
        language can be kept instead of reconnecting twice (new default, then
        the switch back).
        """
        language = self._stack.language_state.get('current_language')
        agent = configs.get('agent') or {}
        supported = agent.get('supported_languages') or []
        if (
            not language
            or language not in supported
            or language == agent.get('default_language')
        ):
            return configs
        logger.info(f'Agent swap carries the conversation language {language!r}')
        # The configs may be cached for the room: never mutate them
        return {**configs, 'agent': {**agent, 'default_language': language}}

    @staticmethod
    def _live_service_config(
        stack: AgentStack, config: Dict[str, Any], *, tts: bool
    ) -> Dict[str, Any]:
        """``config`` as the live service runs it, after any language switch.

        A runtime switch (``queue_language_update``) moves the language and,
        for TTS, the voice to that language's voice, if one is configured.
        """
        language = stack.language_state.get('current_language')
        parameters = config.get('parameters') or {}
        if not language or parameters.get('language') in (None, language):
            return config
        live = {**config, 'parameters': {**parameters, 'language': language}}
        if tts and stack.tts_voice_ids.get(language):
            live['voice_id'] = stack.tts_voice_ids[language]
        return live

    def _slots_to_swap(
        self, new_stack: AgentStack
    ) -> List[Tuple[SwappableSlot, List[Any]]]:
        """The slots the new stack needs, keeping a live STT/TTS where possible.

        A service is kept when the new agent would create it from the config the
        live one is running with (provider, credentials, voice, parameters,
        sample rate and current language). The new stack then adopts the live
        service, so the next swap compares against it too.
        """
        old_stack = self._stack

        def keep(kind: str, new_config: Dict[str, Any], old_config: Dict[str, Any]):
            live_config = self._live_service_config(
                old_stack, old_config, tts=kind == 'TTS'
            )
            reason = _service_change_reason(new_config, live_config)
            if reason is None:
                logger.info(f'Agent swap keeps the live {kind} service')
                return True
            logger.info(f'Agent swap replaces the {kind} service: {reason}')
            return False

        slots: List[Tuple[SwappableSlot, List[Any]]] = []
        if keep('STT', new_stack.stt_config, old_stack.stt_config):
            new_stack.stt = old_stack.stt
        else:
            slots.append((self._slot_stt, [new_stack.stt]))
        slots.append((self._slot_a, new_stack.slot_a_processors))
        if keep('TTS', new_stack.tts_config, old_stack.tts_config):
            new_stack.tts = old_stack.tts
        else:
            slots.append((self._slot_tts, [new_stack.tts]))
        slots.append((self._slot_b, new_stack.slot_b_processors))
        return slots

    async def _finish_commit(
        self,
        old_stack: AgentStack,
        new_stack: AgentStack,
        replaced: List[Tuple[SwappableSlot, _Inner]],
    ) -> None:
        try:
            await self._messenger.interrupt()
        except Exception as e:
            logger.warning(f'Could not interrupt old agent speech: {e}')
        await self._retire_all(replaced)

        # 5. Rebind the shared pieces to the new stack.
        self._messenger.rebind(
            context=new_stack.context,
            function_schemas=new_stack.function_schemas,
            language_state=new_stack.language_state,
            supported_languages=new_stack.supported_languages,
            tts_provider=new_stack.tts_provider,
            stt_provider=new_stack.stt_provider,
            tts_voice_ids=new_stack.tts_voice_ids,
        )

        # 6. Tell the new agent it took over. If an app step is active, the
        #    step opener (queued by ``finish_swap``) makes it speak, so the note
        #    only needs to be in the context (run_llm=False).
        reopen = self._messenger.will_reopen_step()
        carry = self._options.carry_history
        if carry or not reopen:
            # Without history and with an app step to open, the step opener alone
            # starts the new agent: there is nothing to hand over.
            note = build_handoff_note(
                old_stack.agent_name,
                new_stack.agent_name,
                new_step=reopen,
                carry_history=carry,
            )
            await self._task.queue_frame(
                LLMMessagesAppendFrame(
                    messages=[{'role': 'user', 'content': note}],
                    run_llm=not reopen,
                )
            )

        # 7. Bookkeeping + tell the browser.
        callback = self._options.on_agent_switched
        if callback is not None:
            try:
                result = callback(new_stack.agent_id)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f'on_agent_switched callback failed: {e}')
        await self._messenger.emit_agent_changed(
            new_stack.agent_id, new_stack.agent_name
        )
        logger.info(
            f'Swapped agent {old_stack.agent_id} -> {new_stack.agent_id} '
            f'(swap #{self._swap_count})'
        )

    async def _prepare_all(
        self, slots: List[Tuple[SwappableSlot, List[Any]]]
    ) -> List[Tuple[SwappableSlot, _Inner]]:
        results = await asyncio.gather(
            *(slot.prepare(processors) for slot, processors in slots),
            return_exceptions=True,
        )
        prepared = [
            (slot, result)
            for (slot, _), result in zip(slots, results)
            if not isinstance(result, BaseException)
        ]
        failures = [r for r in results if isinstance(r, BaseException)]
        if failures:
            # Do not leave a half-started stack behind
            await self._retire_all(prepared)
            first = failures[0]
            if isinstance(first, asyncio.CancelledError):
                raise first
            logger.error(f'New agent stack failed to start: {first}')
            raise SwapError(ERR_SWAP_FAILED)
        return prepared

    @staticmethod
    async def _retire_all(inners: List[Tuple[SwappableSlot, _Inner]]) -> None:
        await asyncio.gather(
            *(slot.retire(inner) for slot, inner in inners),
            return_exceptions=True,
        )

    @staticmethod
    def _seed_context(new_stack: AgentStack, old_stack: AgentStack) -> None:
        """New system prompt + the old conversation's user/assistant text turns."""
        history = build_handoff_history(old_stack.context.get_messages())
        current = new_stack.context.get_messages()
        system = [
            m for m in current[:1] if isinstance(m, dict) and m.get('role') == 'system'
        ]
        new_stack.context.set_messages([*system, *history])
