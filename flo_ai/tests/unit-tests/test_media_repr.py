"""A media message's repr never includes its payload.

Messages are formatted into logs, error-analysis prompts and span attributes;
a repr that carried the base64 copied the whole file into each of them.
"""

import pytest

from flo_ai import (
    DocumentMessageContent,
    ImageMessageContent,
    UserMessage,
    VideoMessageContent,
)

MEDIA = [ImageMessageContent, DocumentMessageContent, VideoMessageContent]


@pytest.mark.parametrize('media', MEDIA)
def test_repr_leaves_out_base64_and_bytes(media):
    content = media(base64='A' * 10_000, bytes=b'\x00' * 10_000, mime_type='x/y')

    text = repr(content)

    assert len(text) < 200
    assert 'AAAA' not in text
    assert "mime_type='x/y'" in text


def test_message_repr_stays_small():
    message = UserMessage(content=DocumentMessageContent(base64='A' * 10_000))

    assert len(repr(message)) < 300


@pytest.mark.parametrize('media', MEDIA)
def test_equality_still_compares_the_payload(media):
    assert media(base64='a') != media(base64='b')
    assert media(base64='a') == media(base64='a')
