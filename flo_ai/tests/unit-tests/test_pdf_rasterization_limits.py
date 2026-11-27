"""Limits on rasterizing a PDF for providers without native PDF input.

Every page becomes an image held in memory until the last is rendered, and a
PDF can declare any page size, so both the page count and each page's pixel
size are capped before anything is allocated.
"""

import base64
import os
import struct
import subprocess
import sys

import pymupdf
import pytest

from flo_ai import DocumentMessageContent, UserMessage
from flo_ai.agent import Agent
from flo_ai.llm import base_llm
from flo_ai.llm.base_llm import BaseLLM
from flo_ai.llm.openai_llm import OpenAI
from flo_ai.models.agent_error import AgentError
from flo_ai.utils.document_text_extraction import (
    MAX_PDF_PAGE_SIDE,
    MAX_PDF_PAGES,
    DocumentTooLarge,
)

LETTER = (612, 792)


def _pdf(pages: int = 1, size=LETTER) -> DocumentMessageContent:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=size[0], height=size[1])
    data = doc.tobytes()
    doc.close()
    return DocumentMessageContent(
        base64=base64.b64encode(data).decode(), mime_type='application/pdf'
    )


def _png_sizes(blocks):
    """(width, height) of each rasterized page, read from its PNG header."""
    sizes = []
    for block in blocks:
        if block.get('type') != 'image_url':
            continue
        png = base64.b64decode(block['image_url']['url'].split(',', 1)[1])
        sizes.append(struct.unpack('>II', png[16:24]))
    return sizes


@pytest.fixture
def no_rendering(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError('a page was rendered')

    monkeypatch.setattr(pymupdf.Page, 'get_pixmap', refuse)


class TestPageCount:
    async def test_over_the_limit_fails_before_rendering(self, no_rendering):
        document = _pdf(pages=MAX_PDF_PAGES + 1)

        with pytest.raises(DocumentTooLarge) as raised:
            await OpenAI(api_key='k').format_document_in_message(document)

        assert str(raised.value) == (
            f'PDF has {MAX_PDF_PAGES + 1} pages; the limit is {MAX_PDF_PAGES}.'
        )

    async def test_at_the_limit_renders_every_page(self, monkeypatch):
        monkeypatch.setattr(base_llm, 'MAX_PDF_PAGES', 3)

        blocks = await OpenAI(api_key='k').format_document_in_message(_pdf(pages=3))

        assert len(_png_sizes(blocks)) == 3

    async def test_failure_is_not_cached(self, monkeypatch, no_rendering):
        monkeypatch.setattr(base_llm, 'MAX_PDF_PAGES', 1)
        document = _pdf(pages=2)

        with pytest.raises(DocumentTooLarge):
            await OpenAI(api_key='k').format_document_in_message(document)

        assert document._formatted_cache == {}


class TestPageSize:
    async def test_letter_page_keeps_the_requested_dpi(self):
        blocks = await OpenAI(api_key='k').format_document_in_message(_pdf())

        assert _png_sizes(blocks) == [(1275, 1650)]

    async def test_oversized_page_is_scaled_to_fit(self):
        # 200 x 100 inches: 30000 x 15000 px at 150 DPI.
        document = _pdf(size=(14400, 7200))

        blocks = await OpenAI(api_key='k').format_document_in_message(document)

        assert _png_sizes(blocks) == [(MAX_PDF_PAGE_SIDE, MAX_PDF_PAGE_SIDE // 2)]

    async def test_higher_dpi_is_capped_too(self):
        llm = OpenAI(api_key='k')
        llm.kwargs['pdf_raster_dpi'] = 600

        blocks = await llm.format_document_in_message(_pdf())

        [(width, height)] = _png_sizes(blocks)
        assert height == MAX_PDF_PAGE_SIDE
        assert width < MAX_PDF_PAGE_SIDE


class RasterizingLLM(BaseLLM):
    """Uses the default rasterizing document path; counts every model call."""

    def __init__(self):
        super().__init__(model='fake-model', api_key='key')
        self.calls = 0

    async def generate(self, messages, functions=None, output_schema=None):
        self.calls += 1
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


async def test_agent_fails_without_asking_the_model_to_analyse_it(monkeypatch):
    """Error analysis would send the whole history, the PDF's base64 included,
    to the model as text. A file that is too large is final instead."""
    monkeypatch.setattr(base_llm, 'MAX_PDF_PAGES', 1)
    llm = RasterizingLLM()
    agent = Agent(name='reader', system_prompt='Read.', llm=llm, max_retries=2)

    with pytest.raises(AgentError) as raised:
        await agent.run([UserMessage(content=_pdf(pages=2))])

    assert isinstance(raised.value.original_error, DocumentTooLarge)
    assert 'PDF has 2 pages; the limit is 1.' in str(raised.value)
    assert llm.calls == 0


def test_limits_are_read_from_the_environment():
    code = (
        'from flo_ai.utils.document_text_extraction import '
        'MAX_PDF_PAGES, MAX_PDF_PAGE_SIDE; '
        'print(MAX_PDF_PAGES, MAX_PDF_PAGE_SIDE)'
    )
    env = {
        **os.environ,
        'DOCUMENT_MAX_PDF_PAGES': '7',
        'DOCUMENT_MAX_PDF_PAGE_SIDE': '1024',
    }

    output = subprocess.run(
        [sys.executable, '-c', code], env=env, capture_output=True, text=True
    )

    assert output.stdout.split() == ['7', '1024']


def test_defaults():
    assert (MAX_PDF_PAGES, MAX_PDF_PAGE_SIDE) == (50, 2048)
