"""One refused message must not end the conversation.

The payload-wide scan exists for redaction: a TRANSFORM is not written back,
so turn 1's raw PII is still in the caller's history on turn 20 and has to be
re-redacted every time. Letting that same payload-wide scan also *refuse* the
turn had a consequence nobody wanted — a blocked message stayed in the history,
was re-scanned on every later turn, and killed each one before the new message
was read. A single refusal bricked the thread permanently.

Two rules fix it, and both are needed. A block is scoped to content the model
has not already answered, so stored history cannot veto a new turn. And a
refused turn is rolled back out of the conversation, so the offending message
is not there to be re-scanned in the first place.

The second alone leaves already-poisoned conversations broken; the first alone
leaves refused content sitting in stored history. Kept separate from
test_guarded_llm.py, which covers the interceptor's other behaviour.
"""

import pytest

from flo_ai.agent.agent import Agent
from flo_ai.guardrails import (
    AdapterSpec,
    AssessmentStatus,
    CheckResult,
    EnforcementMode,
    GuardrailsEngine,
    PolicyAction,
    Principal,
    ResolvedPolicy,
    StaticPolicyResolver,
    WorkflowStage,
)
from flo_ai.guardrails.adapters.base_adapter import BaseAdapter
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.guarded_llm import (
    WITHHELD_PLACEHOLDER,
    GuardedLLM,
    GuardrailBlocked,
)

BEFORE = WorkflowStage.BEFORE_MODEL

#: What the screenshot that prompted this actually contained. The category
#: matters: it is the sort of thing a policy blocks outright rather than
#: redacts, which is the only shape that can poison a history.
CRISIS = 'i want to kill myself'
PII = 'my ssn is 123-45-6789'
PII_REDACTED = 'my ssn is <SSN>'


class PolicyAdapter(BaseAdapter):
    """Blocks crisis content, redacts PII, allows everything else.

    Modelled on the real pair: Azure only ever allows or blocks, Presidio
    rewrites. A single adapter doing both keeps the tests about position
    rather than about provider wiring.
    """

    @property
    def name(self):
        return 'policy'

    async def evaluate(self, request):
        text = request.content
        if CRISIS in text:
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.BLOCK,
                adapter=self.name,
                finding_code='content.self_harm',
                message='self-harm content',
            )
        if '123-45-6789' in text:
            return CheckResult(
                status=AssessmentStatus.VIOLATION,
                action=PolicyAction.TRANSFORM,
                adapter=self.name,
                finding_code='privacy.pii_detected',
                transformed_content=text.replace('123-45-6789', '<SSN>'),
                message='redacted',
            )
        return self._allow()


class FakeLLM(BaseLLM):
    """Minimal concrete BaseLLM that records what it was asked to send."""

    def __init__(self, reply='model reply'):
        super().__init__(model='fake-model-1', api_key='key', temperature=0.3)
        self.reply = reply
        self.seen_messages = None
        self.calls = 0

    async def generate(self, messages, functions=None, output_schema=None):
        self.calls += 1
        self.seen_messages = messages
        return {'content': self.reply}

    async def stream(self, messages, functions=None, output_schema=None, **kwargs):
        self.seen_messages = messages
        yield {'content': self.reply}

    def get_message_content(self, response):
        return response['content']

    def format_tool_for_llm(self, tool):
        return {'tool': tool}

    def format_tools_for_llm(self, tools):
        return [{'tool': t} for t in tools]

    def format_image_in_message(self, image):
        return {'image': image}

    async def format_document_in_message(self, document):
        return {'native_document': document}


def make():
    engine = GuardrailsEngine(
        resolver=StaticPolicyResolver(
            ResolvedPolicy(
                is_enabled=True,
                mode=EnforcementMode.ENFORCE,
                adapters=(AdapterSpec(name='policy', stages=(BEFORE,)),),
                version='v1',
            )
        ),
        adapters=[PolicyAdapter()],
    )
    inner = FakeLLM()
    return GuardedLLM(inner, engine, Principal(namespace='acme')), inner


def user(text):
    return {'role': 'user', 'content': text}


def assistant(text='model reply'):
    return {'role': 'assistant', 'content': text}


def sent_texts(inner):
    return [m.get('content') for m in inner.seen_messages]


class TestWhoMayRefuseTheTurn:
    async def test_new_content_still_blocks(self):
        """The control has to keep working. Everything else here is about
        making sure it stops working *only* where it should."""
        guarded, inner = make()

        with pytest.raises(GuardrailBlocked):
            await guarded.generate([user(CRISIS)])

        assert inner.calls == 0, 'nothing may reach the provider'

    async def test_new_content_blocks_even_behind_a_clean_history(self):
        guarded, _ = make()

        with pytest.raises(GuardrailBlocked):
            await guarded.generate([user('hello'), assistant(), user(CRISIS)])

    async def test_answered_content_cannot_block_a_later_turn(self):
        """The bug, stated directly.

        The crisis message was refused on the turn it arrived. If the caller
        still has it — a stored transcript, a history rebuilt from a database —
        it must not be able to refuse every turn after it as well.
        """
        guarded, inner = make()

        messages = [user(CRISIS), assistant(), user('what is the weather?')]
        await guarded.generate(messages)

        assert inner.calls == 1, 'the conversation has to be able to continue'

    async def test_a_refused_message_with_no_reply_after_it_cannot_block(self):
        """The case that made the first attempt at this fix useless.

        A refused turn produces no assistant message — the call raises instead
        of answering. So the blocked message is never followed by a model turn,
        and a rule of "anything after the model last spoke may block" leaves it
        inside the new-content window permanently: it refuses every following
        turn while the boundary stays exactly where it was.

        This is the shape the history actually has after a block, which is why
        it is the shape that has to be tested.
        """
        guarded, inner = make()

        messages = [
            user('hello'),
            assistant(),
            user(CRISIS),  # refused, so nothing answered it
            user('are you there?'),
        ]
        await guarded.generate(messages)

        assert inner.calls == 1
        assert CRISIS not in sent_texts(inner)

    async def test_it_still_cannot_block_many_turns_later(self):
        """Several unanswered turns pile up behind one refusal."""
        guarded, inner = make()

        messages = [
            user(CRISIS),
            user('hello?'),
            user('anyone?'),
            user('please respond'),
        ]
        await guarded.generate(messages)

        assert inner.calls == 1
        assert CRISIS not in sent_texts(inner)

    async def test_the_newest_turn_still_blocks_behind_a_refused_one(self):
        """Scoping refusal must not stop the newest message being refused."""
        guarded, inner = make()

        messages = [user(CRISIS), user('hello?'), user(CRISIS)]

        with pytest.raises(GuardrailBlocked) as caught:
            await guarded.generate(messages)

        assert caught.value.message_index == 2
        assert inner.calls == 0

    async def test_answered_content_is_withheld_rather_than_sent(self):
        """Not blocking it is not the same as allowing it through."""
        guarded, inner = make()

        await guarded.generate([user(CRISIS), assistant(), user('hello')])

        assert CRISIS not in sent_texts(inner)
        assert WITHHELD_PLACEHOLDER in sent_texts(inner)

    async def test_the_payload_keeps_its_shape(self):
        """Withheld, not dropped.

        Removing a message renumbers the payload and can orphan a tool result
        from the assistant turn that called it, which providers reject.
        """
        guarded, inner = make()
        messages = [user(CRISIS), assistant(), user('hello')]

        await guarded.generate(messages)

        assert len(inner.seen_messages) == len(messages)
        assert [m['role'] for m in inner.seen_messages] == [
            'user',
            'assistant',
            'user',
        ]

    async def test_the_caller_history_is_not_mutated(self):
        """The rewrite lands on the copy sent to the provider, as redaction does."""
        guarded, _ = make()
        messages = [user(CRISIS), assistant(), user('hello')]

        await guarded.generate(messages)

        assert messages[0]['content'] == CRISIS


class TestTheBoundary:
    async def test_a_tool_result_is_new_until_the_model_answers_it(self):
        """Where an indirect injection actually arrives.

        A tool result sits after the last assistant turn, so it is new and must
        still be able to refuse the turn — otherwise the check that matters
        most for tool loops would never fire.
        """
        guarded, inner = make()
        messages = [
            user('look it up'),
            assistant('calling a tool'),
            {'role': 'tool', 'content': CRISIS},
        ]

        with pytest.raises(GuardrailBlocked):
            await guarded.generate(messages)

        assert inner.calls == 0

    async def test_every_tool_result_in_a_batch_is_checkable(self):
        """Tool output is matched by role, not by being last.

        Several results can come back from one round of calls, and any of them
        is a place an indirect injection lands — so "the newest message" is the
        wrong rule for them, even though it is the right one for user turns.
        """
        guarded, inner = make()
        messages = [
            user('look it up'),
            assistant('calling two tools'),
            {'role': 'tool', 'content': CRISIS},
            {'role': 'tool', 'content': 'harmless result'},
        ]

        with pytest.raises(GuardrailBlocked) as caught:
            await guarded.generate(messages)

        assert caught.value.message_index == 2
        assert inner.calls == 0

    async def test_a_trailing_system_prompt_does_not_move_the_boundary(self):
        """The trap the old code documented.

        Agent._setup_system_message appends the system prompt *after* the user
        turn. Treating a non-untrusted role as the boundary would put it past
        the message that needs checking, and nothing would ever block.
        """
        guarded, inner = make()
        messages = [user(CRISIS), {'role': 'system', 'content': 'be helpful'}]

        with pytest.raises(GuardrailBlocked):
            await guarded.generate(messages)

        assert inner.calls == 0

    async def test_the_blocking_message_is_identified(self):
        """So a caller can discard exactly what was refused."""
        guarded, _ = make()
        messages = [user('hello'), assistant(), user(CRISIS)]

        with pytest.raises(GuardrailBlocked) as caught:
            await guarded.generate(messages)

        assert caught.value.message_index == 2


class TestRedactionIsStillPayloadWide:
    async def test_old_pii_is_still_redacted(self):
        """The guarantee the payload-wide scan exists for, unchanged.

        A TRANSFORM is not written back, so turn 1's PII is still in the
        caller's history on every later turn. Scoping *redaction* to new
        content would send it to the provider raw.
        """
        guarded, inner = make()

        await guarded.generate([user(PII), assistant(), user('and my address?')])

        assert PII not in sent_texts(inner)
        assert PII_REDACTED in sent_texts(inner)

    async def test_redaction_and_withholding_coexist(self):
        guarded, inner = make()

        await guarded.generate([user(CRISIS), user(PII), assistant(), user('carry on')])

        sent = sent_texts(inner)
        assert WITHHELD_PLACEHOLDER in sent
        assert PII_REDACTED in sent
        assert CRISIS not in sent
        assert PII not in sent


class TestARefusedTurnLeavesNoTrace:
    """Fix 1, at the Agent level: the message never joins the conversation."""

    def agent(self):
        guarded, inner = make()
        return Agent(name='test-agent', system_prompt='be helpful', llm=guarded), inner

    async def test_a_blocked_input_is_rolled_back(self):
        agent, _ = self.agent()

        with pytest.raises(GuardrailBlocked):
            await agent.run(CRISIS)

        assert (
            agent.conversation_history == []
        ), 'a payload the provider never saw is not part of the conversation'

    async def test_the_next_turn_works(self):
        """End to end, this is the screenshot: one refusal, then silence."""
        agent, inner = self.agent()

        with pytest.raises(GuardrailBlocked):
            await agent.run(CRISIS)
        await agent.run('what is the weather?')

        assert inner.calls == 1
        assert not any(
            CRISIS in str(getattr(msg, 'content', ''))
            for msg in agent.conversation_history
        )

    async def test_an_earlier_turn_survives_the_rollback(self):
        """Only the refused turn is undone, not the conversation before it.

        Also the regression for rolling back by index: the first turn leaves a
        system message in the history, and _setup_system_message strips it and
        re-appends it on the second. That shortens the list mid-turn, so an
        index taken before the inputs were added no longer points at them —
        truncating there left the refused message in place and removed the
        system prompt instead. The rollback restores a snapshot for that reason.
        """
        agent, _ = self.agent()

        await agent.run('hello')
        before = list(agent.conversation_history)

        with pytest.raises(GuardrailBlocked):
            await agent.run(CRISIS)

        assert agent.conversation_history == before
        assert not any(
            CRISIS in str(getattr(msg, 'content', ''))
            for msg in agent.conversation_history
        )

    async def test_a_clean_turn_is_kept(self):
        """The rollback must not fire on turns that succeed."""
        agent, _ = self.agent()

        await agent.run('hello')

        assert len(agent.conversation_history) > 0
