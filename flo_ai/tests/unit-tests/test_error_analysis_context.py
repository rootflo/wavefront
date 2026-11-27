"""The error-analysis prompt is bounded and never carries a file's payload.

On a non-provider error the agent asks the model to analyse it. That prompt
used to embed the whole conversation history, so one attached document put its
entire base64 into the prompt as text - larger than any context window.
"""

import base64

import pytest

from flo_ai import DocumentMessageContent, UserMessage
from flo_ai.agent import Agent
from flo_ai.agent.base_agent import ERROR_ANALYSIS_CONTEXT_CHARS
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.models.agent_error import AgentError
from flo_ai.utils.document_text_extraction import DocumentExtractionError

PDF = 'application/pdf'
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


class AnalysingLLM(BaseLLM):
    """Optionally fails the first call; records every error-analysis prompt."""

    def __init__(self, first_call_error=None):
        super().__init__(model='fake-model', api_key='key')
        self.first_call_error = first_call_error
        self.calls = 0
        self.prompts = []

    async def generate(self, messages, functions=None, output_schema=None):
        self.calls += 1
        if self.calls == 1 and self.first_call_error is not None:
            raise self.first_call_error
        self.prompts.append(messages[-1]['content'])
        return {'content': 'This is not recoverable.'}

    async def stream(self, messages, functions=None, output_schema=None, **kwargs):
        yield {'content': ''}

    def get_message_content(self, response):
        return response['content']

    def format_tool_for_llm(self, tool):
        return {'tool': tool}

    def format_tools_for_llm(self, tools):
        return [{'tool': t} for t in tools]

    def format_image_in_message(self, image):
        return {'image': image}


class NativeDocumentLLM(AnalysingLLM):
    async def format_document_in_message(self, document):
        return {'document': 'formatted'}


async def _analysis_prompt(inputs, error=None) -> str:
    llm = NativeDocumentLLM(error or ValueError('reply could not be parsed'))
    agent = Agent(name='reader', system_prompt='Read.', llm=llm)

    with pytest.raises(AgentError):
        await agent.run(inputs)

    [prompt] = llm.prompts
    return prompt


def _pdf(size: int) -> DocumentMessageContent:
    # Distinctive base64, so any leak of it into the prompt is detectable.
    return DocumentMessageContent(base64='QUJD' * (size // 4), mime_type=PDF)


async def test_document_appears_as_a_label_not_its_payload():
    prompt = await _analysis_prompt(
        [UserMessage(content=_pdf(1_000_000)), UserMessage('Summarise this')]
    )

    assert 'QUJDQUJD' not in prompt
    assert '[document: application/pdf]' in prompt
    assert 'Summarise this' in prompt


async def test_prompt_size_does_not_depend_on_the_file_size():
    small = await _analysis_prompt([UserMessage(content=_pdf(1_000_000))])
    large = await _analysis_prompt([UserMessage(content=_pdf(4_000_000))])

    assert len(small) == len(large)


async def test_only_the_last_messages_are_included():
    prompt = await _analysis_prompt([UserMessage(f'msg-{i}') for i in range(8)])

    assert 'msg-7' in prompt
    assert 'msg-0' not in prompt


async def test_long_text_is_clipped():
    prompt = await _analysis_prompt([UserMessage('x' * 5_000)])

    assert '[truncated, 5000 characters in total]' in prompt
    assert 'x' * 1_001 not in prompt


async def test_long_error_is_clipped():
    prompt = await _analysis_prompt(
        [UserMessage('hello')], error=ValueError('e' * 10_000)
    )

    assert '[truncated, 10000 characters in total]' in prompt
    assert 'e' * 2_001 not in prompt


async def test_any_context_is_clipped():
    """The tool-call path passes its own context; it is bounded too."""
    llm = AnalysingLLM()
    agent = Agent(name='reader', system_prompt='Read.', llm=llm)

    await agent.handle_error(
        ValueError('bad arguments'), {'function_call': {'arguments': 'y' * 50_000}}
    )

    [prompt] = llm.prompts
    assert '[truncated,' in prompt
    assert len(prompt) < ERROR_ANALYSIS_CONTEXT_CHARS + 1_000


async def test_overrides_still_receive_the_full_history():
    """`handle_error` is overridable: its context keeps its original shape, the
    real message objects included. Only the prompt it builds is bounded."""
    received = []

    class InspectingAgent(Agent):
        async def handle_error(self, error, context):
            received.append(context)
            return await super().handle_error(error, context)

    document = _pdf(1_000_000)
    llm = NativeDocumentLLM(ValueError('reply could not be parsed'))
    agent = InspectingAgent(name='reader', system_prompt='Read.', llm=llm)

    with pytest.raises(AgentError):
        await agent.run([UserMessage(content=document)])

    [context] = received
    assert context['conversation_history'][0].content is document
    [prompt] = llm.prompts
    assert 'QUJDQUJD' not in prompt


def _corrupt_docx() -> DocumentMessageContent:
    return DocumentMessageContent(
        base64=base64.b64encode(b'not a docx').decode(), mime_type=DOCX
    )


async def test_unreadable_document_fails_without_analysis():
    """Analysing a corrupt upload cannot fix it, and retrying fails the same way."""
    llm = AnalysingLLM()
    agent = Agent(name='reader', system_prompt='Read.', llm=llm, max_retries=2)

    with pytest.raises(AgentError) as raised:
        await agent.run([UserMessage(content=_corrupt_docx())])

    assert isinstance(raised.value.original_error, DocumentExtractionError)
    assert llm.calls == 0


async def test_rejected_document_is_not_kept_for_later_runs():
    """Kept in the history, it would fail every later run of the agent too."""
    llm = AnalysingLLM()
    agent = Agent(name='reader', system_prompt='Read.', llm=llm)

    with pytest.raises(AgentError):
        await agent.run([UserMessage(content=_corrupt_docx())])
    await agent.run('hello')

    assert llm.calls == 1
    assert not any(
        isinstance(m.content, DocumentMessageContent)
        for m in agent.conversation_history
    )
