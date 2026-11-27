"""The agent's request log never formats the request payload.

It used to be an f-string, built on every LLM call whatever the log level, and
the provider request holds every attached image and rendered page as base64.
"""

import logging

import pytest

from flo_ai import DocumentMessageContent, UserMessage
from flo_ai.agent import Agent
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.utils.logger import logger as flo_logger

PAGE = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,QUJDQUJD'}}


class Sentinel:
    """Counts every attempt to turn it into text."""

    def __init__(self):
        self.formatted = 0

    def __repr__(self):
        self.formatted += 1
        return 'sentinel'

    __str__ = __repr__


class FakeLLM(BaseLLM):
    def __init__(self, document_content):
        super().__init__(model='fake-model', api_key='key')
        self.document_content = document_content

    async def generate(self, messages, functions=None, output_schema=None):
        return {'content': 'reply'}

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

    async def format_document_in_message(self, document):
        return self.document_content


def _document_message():
    return UserMessage(content=DocumentMessageContent(base64='QUJD', mime_type='x/y'))


@pytest.fixture
def flo_records(caplog):
    """`flo_ai` does not propagate to the root logger, so attach to it directly."""
    flo_logger.addHandler(caplog.handler)
    previous = flo_logger.level
    yield caplog
    flo_logger.removeHandler(caplog.handler)
    flo_logger.setLevel(previous)


async def test_payload_is_not_formatted_above_debug(flo_records):
    flo_logger.setLevel(logging.INFO)
    sentinel = Sentinel()
    agent = Agent(name='reader', system_prompt='Read.', llm=FakeLLM(sentinel))

    await agent.run([_document_message()])

    assert sentinel.formatted == 0


async def test_debug_log_describes_the_request_without_its_content(flo_records):
    flo_logger.setLevel(logging.DEBUG)
    agent = Agent(name='reader', system_prompt='Read.', llm=FakeLLM([PAGE] * 3))

    await agent.run([_document_message(), UserMessage('Summarise this')])

    [record] = [r for r in flo_records.records if r.getMessage().startswith('Sending')]
    text = record.getMessage()
    assert 'user(image_url x3)' in text
    assert 'user(text[14 chars])' in text
    assert 'QUJD' not in text
    assert 'Summarise this' not in text
