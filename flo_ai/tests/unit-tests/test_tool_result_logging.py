"""Tool results are logged by type, size and a short preview, never in full.

A result can be a whole query result, a fetched page or a file; it was logged
in full at INFO.
"""

import logging

import pytest

from flo_ai import DocumentMessageContent
from flo_ai.tool.base_tool import Tool, describe_tool_result
from flo_ai.tool.partial_tool import PartialTool
from flo_ai.utils.logger import logger as flo_logger

BIG = 'x' * 1_000_000


@pytest.fixture
def flo_records(caplog):
    """`flo_ai` does not propagate to the root logger, so attach to it directly."""
    flo_logger.addHandler(caplog.handler)
    previous = flo_logger.level
    yield caplog
    flo_logger.removeHandler(caplog.handler)
    flo_logger.setLevel(previous)


def _tool(result):
    async def fetch(**kwargs):
        return result

    return Tool(name='fetch', description='Fetch.', function=fetch, parameters={})


def _result_records(records):
    return [r for r in records if 'returned' in r.getMessage()]


async def test_info_records_size_and_a_short_preview(flo_records):
    flo_logger.setLevel(logging.INFO)

    await _tool(BIG).execute()

    [record] = _result_records(flo_records.records)
    assert record.levelno == logging.INFO
    assert record.getMessage() == 'Tool fetch returned str[1000000 chars]: ' + (
        'x' * 200
    )


async def test_non_text_result_preview_is_cut_too(flo_records):
    flo_logger.setLevel(logging.INFO)

    await _tool({'rows': [BIG]}).execute()

    [record] = _result_records(flo_records.records)
    assert record.getMessage().startswith("Tool fetch returned dict[1 items]: {'rows'")
    assert len(record.getMessage()) < 300


async def test_nothing_is_formatted_above_info(flo_records):
    class Sentinel:
        formatted = 0

        def __repr__(self):
            Sentinel.formatted += 1
            return 'sentinel'

        __str__ = __repr__

    flo_logger.setLevel(logging.WARNING)

    await _tool(Sentinel()).execute()

    assert Sentinel.formatted == 0
    assert _result_records(flo_records.records) == []


async def test_partial_tool_logs_the_same_way_from_its_own_file(flo_records):
    flo_logger.setLevel(logging.INFO)
    partial = PartialTool(_tool(BIG), prefilled_params={})

    await partial.execute()

    [record] = _result_records(flo_records.records)
    assert record.getMessage() == (
        'Partial tool fetch_partial returned str[1000000 chars]: ' + 'x' * 200
    )
    assert record.filename == 'partial_tool.py'


@pytest.mark.parametrize(
    'result, expected',
    [
        ('abc', 'str[3 chars]'),
        ({'a': 1, 'b': 2}, 'dict[2 items]'),
        ([1, 2, 3], 'list[3 items]'),
        (
            DocumentMessageContent(base64='QUJD', mime_type='application/pdf'),
            'DocumentMessageContent(application/pdf)',
        ),
        (42, 'int'),
        (None, 'NoneType'),
    ],
)
def test_describe_tool_result(result, expected):
    assert describe_tool_result(result) == expected
