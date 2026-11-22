"""Formatting the LLM writes must never reach the TTS, whatever the prompt says."""

import pytest

from call_processing.services.common.providers.tts_service import TTSServiceFactory

PROVIDERS = ('elevenlabs', 'deepgram', 'cartesia', 'sarvam', 'azure')


def _tts(provider: str):
    return TTSServiceFactory.create_tts_service(
        {
            'provider': provider,
            'api_key': 'test-key',
            'region': 'eastus',
            'voice_id': 'voice',
            'parameters': {},
        }
    )


async def _spoken(service, text: str) -> str:
    for text_filter in service._text_filters:
        text = await text_filter.filter(text)
    return text


@pytest.mark.parametrize('provider', PROVIDERS)
async def test_markdown_is_not_spoken(provider):
    spoken = await _spoken(
        _tts(provider), '**Sure!** Run `refund` and see *the* [docs](https://x.io).'
    )

    for mark in ('*', '`', '](', 'https://'):
        assert mark not in spoken, (provider, spoken)
    assert 'Sure!' in spoken and 'refund' in spoken


@pytest.mark.parametrize('provider', PROVIDERS)
async def test_numbered_lists_keep_their_numbers(provider):
    spoken = await _spoken(_tts(provider), '1. Check the order')

    assert '1.' in spoken and 'Check the order' in spoken


@pytest.mark.parametrize('provider', PROVIDERS)
def test_each_service_gets_its_own_filters(provider):
    # Filters carry per-stream state; sharing one would leak it between calls
    first, second = _tts(provider), _tts(provider)

    assert first._text_filters[0] is not second._text_filters[0]


async def test_sarvam_skips_a_chunk_that_was_only_formatting_and_emoji():
    assert await _spoken(_tts('sarvam'), '**😊**') == ''
