"""Hot-swapping the voice agent of a live room.

Starts with the spike: a ``SwappableSlot`` inside a real ``PipelineTask`` can
forward frames, be swapped, and the old inner pipeline is cleaned up without the
outer task seeing a second StartFrame or a CancelFrame (which would restart or
disconnect the transport in production).
"""

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from pipecat.frames.frames import (
    CancelFrame,
    Frame,
    InputAudioRawFrame,
    LLMMessagesAppendFrame,
    StartFrame,
    TextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from call_processing.services.agent_stack import AgentStack, SharedSession
from call_processing.services.webrtc_agent_swap import (
    AgentSwapController,
    SwapOptions,
    SwappableSlot,
    build_handoff_history,
    build_handoff_note,
)
from call_processing.services.webrtc_app_messages import (
    OVERLAY_END,
    OVERLAY_START,
    STEP_OPENER,
)
from call_processing.services.webrtc_room_service import (
    ERR_AGENT_NOT_ALLOWED,
    ERR_AGENT_UNAVAILABLE,
    ERR_ALREADY_ACTIVE,
    ERR_SWAP_FAILED,
    ERR_SWAP_IN_PROGRESS,
    ERR_SWAP_LIMIT_REACHED,
)


class Tagger(FrameProcessor):
    """Prefixes downstream text with its tag; records lifecycle events."""

    def __init__(self, tag: str, log: List[tuple], fail_start: bool = False):
        super().__init__(name=f'Tagger-{tag}')
        self.tag = tag
        self.log = log
        self.fail_start = fail_start

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self.log.append(('start', self.tag))
            if self.fail_start:
                await self.push_error('boom')
        elif isinstance(frame, CancelFrame):
            self.log.append(('cancel', self.tag))
        if isinstance(frame, TextFrame) and direction == FrameDirection.DOWNSTREAM:
            await self.push_frame(TextFrame(f'{self.tag}:{frame.text}'), direction)
        else:
            await self.push_frame(frame, direction)

    async def cleanup(self):
        self.log.append(('cleanup', self.tag))
        await super().cleanup()


class Passthrough(FrameProcessor):
    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class Collector(FrameProcessor):
    """Stands in for transport.output(): sees what escapes the slot."""

    def __init__(self):
        super().__init__(name='Collector')
        self.texts: List[str] = []
        self.starts = 0
        self.cancels = 0
        self.audio = 0
        self.started = asyncio.Event()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self.starts += 1
            self.started.set()
        elif isinstance(frame, CancelFrame):
            self.cancels += 1
        elif isinstance(frame, TextFrame):
            self.texts.append(frame.text)
        elif isinstance(frame, InputAudioRawFrame):
            self.audio += 1
        await self.push_frame(frame, direction)


async def _until(predicate, timeout: float = 5.0):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.01)

    await asyncio.wait_for(poll(), timeout)


class Harness:
    def __init__(self, slot: SwappableSlot):
        self.slot = slot
        self.collector = Collector()
        self.task = PipelineTask(
            Pipeline([slot, self.collector]),
            params=PipelineParams(),
            cancel_on_idle_timeout=False,
        )
        self.runner = PipelineRunner(handle_sigint=False)
        self.run: Optional[asyncio.Task] = None

    async def __aenter__(self):
        self.run = asyncio.create_task(self.runner.run(self.task))
        await asyncio.wait_for(self.collector.started.wait(), 5)
        return self

    async def __aexit__(self, *exc):
        await self.task.cancel()
        await asyncio.gather(self.run, return_exceptions=True)


async def test_spike_slot_forwards_swaps_and_cleans_up_old_stack():
    log: List[tuple] = []
    slot = SwappableSlot([Tagger('one', log)], name='slot')

    async with Harness(slot) as h:
        await h.task.queue_frame(TextFrame('a'))
        await _until(lambda: h.collector.texts == ['one:a'])

        new = await slot.prepare([Tagger('two', log)])
        # The old stack keeps serving until the commit
        await h.task.queue_frame(TextFrame('b'))
        await _until(lambda: 'one:b' in h.collector.texts)

        old = slot.commit(new)
        await slot.retire(old)
        await h.task.queue_frame(TextFrame('c'))
        await _until(lambda: 'two:c' in h.collector.texts)

        assert h.collector.texts == ['one:a', 'one:b', 'two:c']
        # Old stack was stopped and cleaned up; the new one was started
        assert ('start', 'two') in log
        assert ('cancel', 'one') in log
        assert ('cleanup', 'one') in log
        # ...and none of that leaked to the outer pipeline
        assert h.collector.starts == 1
        assert h.collector.cancels == 0
        assert not h.run.done()


async def test_spike_upstream_frames_flow_through_the_new_stack_only():
    class Upstreamer(FrameProcessor):
        def __init__(self, tag):
            super().__init__(name=f'Up-{tag}')
            self.tag = tag

        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if isinstance(frame, TextFrame) and direction == FrameDirection.DOWNSTREAM:
                # Reply upstream, like an aggregator reporting back
                await self.push_frame(
                    TextFrame(f'up-{self.tag}'), FrameDirection.UPSTREAM
                )
            await self.push_frame(frame, direction)

    got: List[str] = []

    class Head(FrameProcessor):
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if direction == FrameDirection.UPSTREAM and isinstance(frame, TextFrame):
                got.append(frame.text)
            await self.push_frame(frame, direction)

    slot = SwappableSlot([Upstreamer('one')], name='slot')
    collector = Collector()
    task = PipelineTask(
        Pipeline([Head(name='Head'), slot, collector]),
        params=PipelineParams(),
        cancel_on_idle_timeout=False,
    )
    run = asyncio.create_task(PipelineRunner(handle_sigint=False).run(task))
    try:
        await asyncio.wait_for(collector.started.wait(), 5)
        await task.queue_frame(TextFrame('x'))
        await _until(lambda: got == ['up-one'])

        new = await slot.prepare([Upstreamer('two')])
        await slot.retire(slot.commit(new))
        await task.queue_frame(TextFrame('y'))
        await _until(lambda: got == ['up-one', 'up-two'])
    finally:
        await task.cancel()
        await asyncio.gather(run, return_exceptions=True)


async def test_failed_prepare_leaves_old_stack_untouched():
    log: List[tuple] = []
    slot = SwappableSlot([Tagger('one', log)], name='slot')

    async with Harness(slot) as h:
        with pytest.raises(RuntimeError):
            await slot.prepare([Tagger('bad', log, fail_start=True)])

        await h.task.queue_frame(TextFrame('a'))
        await _until(lambda: h.collector.texts == ['one:a'])
        assert ('cleanup', 'bad') in log
        assert h.collector.cancels == 0


async def test_gated_audio_is_not_forwarded():
    log: List[tuple] = []
    slot = SwappableSlot([Tagger('one', log)], name='slot')

    async with Harness(slot) as h:
        slot.gate_audio(True)
        await h.task.queue_frame(
            InputAudioRawFrame(audio=b'\x00\x00', sample_rate=16000, num_channels=1)
        )
        await h.task.queue_frame(TextFrame('marker'))
        await _until(lambda: 'one:marker' in h.collector.texts)
        assert h.collector.audio == 0

        slot.gate_audio(False)
        await h.task.queue_frame(
            InputAudioRawFrame(audio=b'\x00\x00', sample_rate=16000, num_channels=1)
        )
        await _until(lambda: h.collector.audio == 1)


# ------------------------------------------------------------ history carry-over


def test_handoff_history_strips_overlay_tools_and_system():
    messages = [
        {'role': 'system', 'content': 'old prompt'},
        {'role': 'assistant', 'content': 'Welcome!'},
        {'role': 'user', 'content': STEP_OPENER},
        {'role': 'user', 'content': f'Hi {OVERLAY_START}\nstep\n{OVERLAY_END}'},
        {
            'role': 'assistant',
            'content': None,
            'tool_calls': [{'id': '1', 'function': {'name': 'x'}}],
        },
        {'role': 'tool', 'tool_call_id': '1', 'content': '{}'},
        {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Done.'}]},
        {'role': 'user', 'content': '   '},
        object(),  # provider-specific message objects are skipped
    ]
    assert build_handoff_history(messages) == [
        {'role': 'assistant', 'content': 'Welcome!'},
        {'role': 'user', 'content': 'Hi'},
        {'role': 'assistant', 'content': 'Done.'},
    ]


# ---------------------------------------------------------------- controller


# Fixed UUIDs so pytest-xdist workers collect identical node ids.
A_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
B_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
C_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
D_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'  # not on the allowlist


class FakeMessenger:
    def __init__(self):
        self.events: List[tuple] = []
        self.interrupts = 0
        self.rebound: Optional[Dict[str, Any]] = None
        self.swapping = False
        self.reopen = False

    def begin_swap(self):
        self.swapping = True

    def will_reopen_step(self):
        return self.reopen

    async def finish_swap(self):
        self.swapping = False
        self.events.append(('finish_swap',))

    def rebind(self, **kwargs):
        self.rebound = kwargs

    async def interrupt(self):
        self.interrupts += 1

    async def emit_agent_switching(self, agent_id):
        self.events.append(('switching', agent_id))

    async def emit_agent_changed(self, agent_id, name):
        self.events.append(('changed', agent_id, name))

    async def emit_agent_switch_failed(self, code, message):
        self.events.append(('failed', code))

    def codes(self):
        return [e[1] for e in self.events if e[0] == 'failed']


def make_stack(
    agent_id: str, name: str, log: List[tuple], fail_start=False
) -> AgentStack:
    tagger = Tagger(name, log, fail_start=fail_start)
    assistant = Tagger(f'{name}-asst', log)
    user_aggregator = Passthrough(name=f'{name}-user')
    aggregator = SimpleNamespace(
        user=lambda: user_aggregator, assistant=lambda: assistant
    )
    context = LLMContext([{'role': 'system', 'content': f'prompt of {name}'}])
    return AgentStack(
        agent_config={'id': agent_id, 'name': name, 'welcome_message': 'hi'},
        stt=tagger,
        llm=Passthrough(name=f'{name}-llm'),
        tts=Passthrough(name=f'{name}-tts'),
        context=context,
        context_aggregator=aggregator,
        language_state={'current_language': 'en', 'switch_count': 2},
        function_schemas=[],
        supported_languages=[],
        tts_provider='x',
        stt_provider='x',
        tts_voice_ids={},
        welcome_message='hi',
    )


class ControllerHarness:
    def __init__(
        self,
        *,
        max_swaps=10,
        cooldown=0.0,
        timeout=5.0,
        fail_build=None,
        inactive=(),
        fail_start=False,
        slow_build: Optional[asyncio.Event] = None,
        carry_history: bool = True,
    ):
        self.log: List[tuple] = []
        self.messenger = FakeMessenger()
        self.switched: List[str] = []
        self.names = {A_ID: 'alpha', B_ID: 'beta', C_ID: 'gamma', D_ID: 'delta'}
        self.fail_build = fail_build
        self.fail_start = fail_start
        self.slow_build = slow_build
        self.inactive = set(inactive)

        async def load(agent_uuid):
            if self.slow_build is not None:
                await self.slow_build.wait()
            agent_id = str(agent_uuid)
            if agent_id not in self.names:
                raise KeyError(agent_id)
            status = 'inactive' if agent_id in self.inactive else 'active'
            return {
                'agent': {
                    'id': agent_id,
                    'name': self.names[agent_id],
                    'status': status,
                }
            }

        def build(cfg):
            agent_id = cfg['agent']['id']
            if agent_id == self.fail_build:
                raise RuntimeError('cannot build')
            return make_stack(agent_id, self.names[agent_id], self.log, self.fail_start)

        self.options = SwapOptions(
            allowed_agent_ids={A_ID, B_ID, C_ID},
            load_agent_configs=load,
            on_agent_switched=self.switched.append,
            max_swaps=max_swaps,
            cooldown_secs=cooldown,
            timeout_secs=timeout,
            carry_history=carry_history,
        )
        self.stack = make_stack(A_ID, 'alpha', self.log)
        self.slot_a = SwappableSlot(self.stack.slot_a_processors, name='A')
        self.slot_b = SwappableSlot(self.stack.slot_b_processors, name='B')
        self.collector = Collector()
        self.task = PipelineTask(
            Pipeline([self.slot_a, self.collector, self.slot_b]),
            params=PipelineParams(),
            cancel_on_idle_timeout=False,
        )
        self.queued: List[Frame] = []
        real_queue = self.task.queue_frame

        async def spy_queue(frame):
            self.queued.append(frame)
            await real_queue(frame)

        self.task.queue_frame = spy_queue  # type: ignore[method-assign]
        self.shared = SharedSession(
            call_stats={'agent_switch_count': 0}, transcript_log=[]
        )
        self.shared.active_stack = self.stack
        self.controller = AgentSwapController(
            slot_a=self.slot_a,
            slot_b=self.slot_b,
            task=self.task,
            messenger=self.messenger,
            shared=self.shared,
            build_stack=build,
            stack=self.stack,
            options=self.options,
        )

    async def __aenter__(self):
        self.run = asyncio.create_task(
            PipelineRunner(handle_sigint=False).run(self.task)
        )
        await asyncio.wait_for(self.collector.started.wait(), 5)
        return self

    async def __aexit__(self, *exc):
        await self.controller.close()
        await self.task.cancel()
        await asyncio.gather(self.run, return_exceptions=True)

    async def switch(self, agent_id: str):
        await self.controller.request_switch(agent_id)
        if self.controller._swap_task:
            await self.controller._swap_task


async def test_swap_carries_history_and_switches_prompt():
    async with ControllerHarness() as h:
        h.stack.context.set_messages(
            [
                {
                    'role': 'system',
                    'content': f'prompt of alpha\n\n{OVERLAY_START}\nx\n{OVERLAY_END}',
                },
                {'role': 'assistant', 'content': 'Welcome'},
                {'role': 'user', 'content': 'hello'},
                {'role': 'tool', 'content': '{}', 'tool_call_id': '1'},
            ]
        )
        await h.task.queue_frame(TextFrame('before'))
        await _until(lambda: 'alpha:before' in h.collector.texts)

        await h.switch(B_ID)

        new_stack = h.shared.active_stack
        assert new_stack.agent_id == B_ID
        assert new_stack.context.get_messages() == [
            {'role': 'system', 'content': 'prompt of beta'},
            {'role': 'assistant', 'content': 'Welcome'},
            {'role': 'user', 'content': 'hello'},
        ]
        assert h.controller.current_agent_id == B_ID
        assert h.controller.swap_count == 1
        assert h.shared.call_stats['agent_switch_count'] == 1
        assert h.shared.call_stats['_prior_language_switches'] == 2
        assert h.switched == [B_ID]
        assert h.messenger.rebound['context'] is new_stack.context
        assert h.messenger.interrupts == 1
        assert [e[0] for e in h.messenger.events] == [
            'switching',
            'changed',
            'finish_swap',
        ]
        assert h.messenger.events[1] == ('changed', B_ID, 'beta')

        # Frames now flow through the new stack; the old one is gone
        await h.task.queue_frame(TextFrame('after'))
        await _until(lambda: 'beta:after' in h.collector.texts)
        assert ('cleanup', 'alpha') in h.log
        assert ('cleanup', 'alpha-asst') in h.log
        # The outer pipeline never restarted or cancelled
        assert h.collector.starts == 1
        assert h.collector.cancels == 0

        # The handoff note is queued; it speaks unless an app step will
        notes = [f for f in h.queued if isinstance(f, LLMMessagesAppendFrame)]
        assert len(notes) == 1
        assert 'took over' in notes[0].messages[0]['content']
        assert 'alpha' in notes[0].messages[0]['content']
        assert notes[0].run_llm is True


async def test_handoff_note_does_not_run_llm_when_an_app_step_will_reopen():
    async with ControllerHarness() as h:
        h.messenger.reopen = True
        await h.switch(B_ID)
        note = [f for f in h.queued if isinstance(f, LLMMessagesAppendFrame)][0]
        assert note.run_llm is False
        content = note.messages[0]['content']
        assert 'Do not continue' in content
        assert 'where the conversation left off' not in content


async def test_swap_without_history_starts_the_new_agent_clean():
    async with ControllerHarness(carry_history=False) as h:
        h.stack.context.set_messages(
            [
                {'role': 'system', 'content': 'prompt of alpha'},
                {'role': 'assistant', 'content': 'Welcome'},
                {'role': 'user', 'content': 'my secret is 42'},
            ]
        )

        await h.switch(B_ID)

        new_stack = h.shared.active_stack
        assert new_stack.agent_id == B_ID
        assert new_stack.context.get_messages() == [
            {'role': 'system', 'content': 'prompt of beta'},
        ]
        # The swap itself is unchanged: bookkeeping, rebind and events all happen
        assert h.controller.swap_count == 1
        assert h.switched == [B_ID]
        assert h.messenger.rebound['context'] is new_stack.context
        assert [e[0] for e in h.messenger.events] == [
            'switching',
            'changed',
            'finish_swap',
        ]
        # No earlier conversation to refer to: a fresh-start note that speaks
        (note,) = [f for f in h.queued if isinstance(f, LLMMessagesAppendFrame)]
        content = note.messages[0]['content']
        assert 'no earlier history' in content
        assert 'took over' not in content and 'alpha' not in content
        assert note.run_llm is True


async def test_swap_without_history_lets_the_app_step_start_the_new_agent():
    async with ControllerHarness(carry_history=False) as h:
        h.messenger.reopen = True

        await h.switch(B_ID)

        # The step opener (queued by the messenger) is the only thing that speaks
        assert [f for f in h.queued if isinstance(f, LLMMessagesAppendFrame)] == []
        assert h.shared.active_stack.context.get_messages() == [
            {'role': 'system', 'content': 'prompt of beta'},
        ]
        assert h.messenger.events[-1][0] == 'finish_swap'


def test_handoff_note_variants():
    carried = build_handoff_note('alpha', 'beta')
    assert 'took over' in carried and 'is above' in carried

    fresh = build_handoff_note('alpha', 'beta', carry_history=False)
    assert 'is above' not in fresh and 'alpha' not in fresh
    # Fresh start wins over the new-step variant: there is no "so far" to ignore
    assert fresh == build_handoff_note(
        'alpha', 'beta', new_step=True, carry_history=False
    )


@pytest.mark.parametrize(
    'agent_id,code',
    [
        ('not-a-uuid', ERR_AGENT_NOT_ALLOWED),
        (D_ID, ERR_AGENT_NOT_ALLOWED),
        (A_ID, ERR_ALREADY_ACTIVE),
    ],
)
async def test_switch_rejected_by_precheck(agent_id, code):
    async with ControllerHarness() as h:
        await h.controller.request_switch(agent_id)
        assert h.messenger.codes() == [code]
        assert h.controller.swap_count == 0
        assert not h.messenger.swapping


async def test_unavailable_or_failed_build_keeps_old_agent_running():
    async with ControllerHarness(inactive={B_ID}, fail_build=C_ID) as h:
        await h.switch(B_ID)  # inactive agent
        await h.switch(C_ID)  # factory raises
        assert h.messenger.codes() == [ERR_AGENT_UNAVAILABLE, ERR_SWAP_FAILED]
        assert h.controller.current_agent_id == A_ID
        assert h.switched == []
        assert h.messenger.interrupts == 0

        await h.task.queue_frame(TextFrame('still-alpha'))
        await _until(lambda: 'alpha:still-alpha' in h.collector.texts)
        assert h.collector.cancels == 0
        # The failed attempts still close the swap window
        assert [e[0] for e in h.messenger.events].count('finish_swap') == 2


async def test_new_stack_failing_to_start_keeps_old_agent_running():
    async with ControllerHarness(fail_start=True) as h:
        await h.switch(B_ID)
        assert h.messenger.codes() == [ERR_SWAP_FAILED]
        assert h.controller.current_agent_id == A_ID
        assert ('cleanup', 'beta') in h.log
        await h.task.queue_frame(TextFrame('x'))
        await _until(lambda: 'alpha:x' in h.collector.texts)


async def test_concurrent_swaps_are_rejected():
    gate = asyncio.Event()
    async with ControllerHarness(slow_build=gate) as h:
        await h.controller.request_switch(B_ID)
        assert h.controller.swapping
        await h.controller.request_switch(C_ID)
        assert h.messenger.codes() == [ERR_SWAP_IN_PROGRESS]

        gate.set()
        await h.controller._swap_task
        assert h.controller.current_agent_id == B_ID
        assert h.controller.swap_count == 1


async def test_swap_limit_and_cooldown():
    async with ControllerHarness(max_swaps=5, cooldown=60.0) as h:
        await h.switch(B_ID)
        assert h.controller.swap_count == 1
        await h.switch(C_ID)  # inside the cooldown
        assert h.messenger.codes() == [ERR_SWAP_IN_PROGRESS]

    async with ControllerHarness(max_swaps=1, cooldown=0.0) as h:
        await h.switch(B_ID)
        await h.switch(C_ID)
        assert h.messenger.codes() == [ERR_SWAP_LIMIT_REACHED]
        assert h.controller.current_agent_id == B_ID


async def test_swap_timeout_before_commit_keeps_old_agent():
    gate = asyncio.Event()  # never set: the build hangs
    async with ControllerHarness(slow_build=gate, timeout=0.2) as h:
        await h.switch(B_ID)
        assert h.messenger.codes() == [ERR_SWAP_FAILED]
        assert h.controller.current_agent_id == A_ID
        assert not h.controller.swapping


async def test_close_cancels_in_flight_swap():
    gate = asyncio.Event()
    async with ControllerHarness(slow_build=gate) as h:
        await h.controller.request_switch(B_ID)
        await asyncio.sleep(0.05)
        await h.controller.close()
        assert h.controller._swap_task.done()
        assert h.controller.current_agent_id == A_ID
        assert h.messenger.codes() == []
        # A closed controller admits nothing new
        await h.controller.request_switch(C_ID)
        assert h.messenger.codes() == [ERR_SWAP_FAILED]


async def test_input_frames_are_not_lost_into_the_old_stack_after_swap():
    async with ControllerHarness() as h:
        await h.switch(B_ID)
        for i in range(5):
            await h.task.queue_frame(TextFrame(str(i)))
        await _until(
            lambda: len([t for t in h.collector.texts if t.startswith('beta:')]) == 5
        )
        assert not [t for t in h.collector.texts if t.startswith('alpha:')]
