"""Tests for decoding uploaded text files in any encoding (FileProcessor)."""

from unittest.mock import MagicMock, patch

import pytest

from rag_ingestion.processors import file_processor
from rag_ingestion.processors.file_processor import (
    DocumentType,
    FileProcessor,
    decode_text,
)

ENGLISH = 'The knowledge base indexes every uploaded document for retrieval.\n' * 3
FRENCH = (
    'Le café crème et la crème brûlée sont servis après le déjeuner. '
    'Les élèves étudient à la bibliothèque pendant les vacances d’été.\n'
) * 3
SPANISH = (
    'El niño comió una manzana en el jardín. La señora llegó tarde a la '
    'reunión del miércoles y pidió café con azúcar.\n'
) * 3
JAPANESE = (
    'ナレッジベースはアップロードされたすべての文書を検索のために索引付けします。'
    '日本語の文章も正しく読み込まれる必要があります。\n'
) * 3
SMART_QUOTES = (
    '“Quoted text” and ‘single quotes’ — with an em dash and an ellipsis… '
    'appear in documents exported from Word.\n'
) * 3


@pytest.mark.parametrize(
    ('text', 'encoding'),
    [
        (ENGLISH, 'utf-8'),
        (FRENCH, 'utf-8'),
        (JAPANESE, 'utf-8'),
        (FRENCH, 'utf-16'),
        (JAPANESE, 'utf-16'),
        (SPANISH, 'latin-1'),
        (SMART_QUOTES, 'cp1252'),
        (JAPANESE, 'shift_jis'),
    ],
)
def test_text_in_common_encodings_is_decoded_exactly(text, encoding):
    assert decode_text(text.encode(encoding)) == text


def test_utf8_byte_order_mark_is_stripped():
    assert decode_text('\ufeff'.encode('utf-8') + FRENCH.encode('utf-8')) == FRENCH


def test_empty_file_decodes_to_empty_text():
    assert decode_text(b'') == ''


def test_undetectable_bytes_fall_back_to_utf8_with_replacement():
    no_match = MagicMock()
    no_match.best.return_value = None
    with patch.object(
        file_processor.charset_normalizer, 'from_bytes', return_value=no_match
    ):
        decoded = decode_text(b'valid start \xff\xfe\xfa end')

    assert decoded.startswith('valid start ')
    assert decoded.endswith(' end')
    assert '�' in decoded


def test_utf8_does_not_go_through_detection():
    with patch.object(file_processor.charset_normalizer, 'from_bytes') as detect:
        decode_text(FRENCH.encode('utf-8'))

    detect.assert_not_called()


def test_process_file_decodes_non_utf8_text_files():
    content, document_type = FileProcessor().process_file(
        SPANISH.encode('latin-1'), 'text/plain; charset=iso-8859-1'
    )

    assert document_type == DocumentType.TEXT
    assert content == SPANISH


def test_declared_charset_wins_over_detection():
    # Czech text is valid cp1252 too, just wrong (0xE8 is 'č' in cp1250 but
    # 'è' in cp1252), so only the declaration can tell them apart reliably.
    text = 'Dobrý den, šťastný nový rok a příjemný večer.\n' * 3

    assert decode_text(text.encode('cp1250'), 'windows-1250') == text


@pytest.mark.parametrize('declared', ['no-such-charset', 'ascii'])
def test_unusable_declared_charset_falls_back_to_detection(declared):
    # unknown codec, or one that can't decode these bytes
    assert decode_text(FRENCH.encode('utf-8'), declared) == FRENCH


def test_declared_utf8_strips_the_bom():
    assert (
        decode_text('\ufeff'.encode('utf-8') + ENGLISH.encode('utf-8'), 'UTF-8')
        == ENGLISH
    )


@pytest.mark.parametrize(
    ('file_type', 'expected'),
    [
        ('text/plain', None),
        ('text/plain; charset=utf-16', 'utf-16'),
        ('text/plain;charset="ISO-8859-1"', 'ISO-8859-1'),
        ('text/plain; format=flowed; charset=cp1252', 'cp1252'),
    ],
)
def test_declared_charset_is_read_from_the_mime_type(file_type, expected):
    assert file_processor._declared_charset(file_type) == expected
