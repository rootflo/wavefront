"""
TTS (Text-to-Speech) service factory

Supports ElevenLabs, Deepgram, Cartesia, Sarvam and Azure.
"""

import unicodedata
from dataclasses import replace
from typing import Any, Dict, Optional

from pipecat.frames.frames import TTSUpdateSettingsFrame
from pipecat.services.azure.tts import AzureTTSService, AzureTTSSettings
from pipecat.services.cartesia.tts import CartesiaTTSService, CartesiaTTSSettings
from pipecat.services.deepgram.tts import DeepgramTTSService, DeepgramTTSSettings
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService, ElevenLabsTTSSettings
from pipecat.services.sarvam.tts import (
    TTS_MODEL_CONFIGS,
    SarvamTTSService,
    SarvamTTSSettings,
)
from pipecat.utils.text.base_text_filter import BaseTextFilter
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter

from call_processing.log.logger import logger
from call_processing.services.common.providers.provider_types import TTSProvider
from call_processing.services.common.providers.provider_utils import (
    AZURE_LANGUAGES,
    SARVAM_LANGUAGES,
    map_language,
    pick,
    pick_truthy,
    pipecat_language,
)

# Pipecat 1.12 still only ships bulbul v2/v3; register flash so pipeline
# construction accepts agent configs that select it.
_BULBUL_V4_FLASH = 'bulbul:v4-flash'
if _BULBUL_V4_FLASH not in TTS_MODEL_CONFIGS:
    _base = TTS_MODEL_CONFIGS.get('bulbul:v3') or TTS_MODEL_CONFIGS['bulbul:v2']
    TTS_MODEL_CONFIGS[_BULBUL_V4_FLASH] = replace(_base)

# Emoji, pictographs and the joiners/selectors that glue them together
_UNSPEAKABLE_CATEGORIES = ('So', 'Sk', 'Cs', 'Co')
_UNSPEAKABLE_CHARS = {'‍', '︎', '️'}


class UnspeakableTextFilter(BaseTextFilter):
    """Drops emoji and returns '' when no letters or digits remain.

    Sarvam rejects a chunk like "😊" with a 400 ("Text must contain at least
    one character from the allowed languages") and closes the socket; an empty
    result makes Pipecat skip the chunk instead of sending it.
    """

    async def update_settings(self, settings):
        pass

    async def filter(self, text: str) -> str:
        text = ''.join(
            ch
            for ch in text
            if ch not in _UNSPEAKABLE_CHARS
            and unicodedata.category(ch) not in _UNSPEAKABLE_CATEGORIES
        )
        if not any(ch.isalnum() for ch in text):
            return ''
        return text

    async def handle_interruption(self):
        pass

    async def reset_interruption(self):
        pass


def _text_filters(*extra: BaseTextFilter) -> list:
    """Fresh filters per service (they hold per-stream state).

    Markdown goes first, whatever the prompt asks for: LLMs still emit
    ``**bold**``, lists and backticks, which TTS reads aloud or stumbles on.
    """
    return [MarkdownTextFilter(), *extra]


class TTSServiceFactory:
    """Factory for creating TTS service instances from configuration"""

    @staticmethod
    def create_tts_service(tts_config: Dict[str, Any]):
        """Build a Pipecat TTS service from a stored TTS config.

        Reads ``provider`` (a ``TTSProvider``), ``api_key``, ``voice_id``,
        ``region`` (Azure only) and provider ``parameters`` such as ``model``.
        """
        provider = tts_config['provider']
        api_key = tts_config['api_key']
        voice_id = tts_config['voice_id']
        parameters = tts_config.get('parameters') or {}

        logger.info(f'Creating TTS service: {provider} / voice: {voice_id}')

        if provider == TTSProvider.AZURE:
            return _create_azure_tts(
                api_key, voice_id, tts_config.get('region'), parameters
            )
        create = _CREATORS.get(provider)
        if create is None:
            raise ValueError(f'Unsupported TTS provider: {provider}')
        return create(api_key, voice_id, parameters)

    @staticmethod
    def create_language_update_frame(
        provider: str, lang_code: str, voice_id: Optional[str] = None
    ) -> Optional[TTSUpdateSettingsFrame]:
        """Create TTSUpdateSettingsFrame for a runtime language+voice switch, provider-aware."""
        if provider in (TTSProvider.ELEVENLABS, TTSProvider.DEEPGRAM):
            # Language is implicit in the voice; only the voice changes
            if not voice_id:
                logger.warning(
                    f'{provider} TTS: no voice_id provided for language update'
                )
                return None
            settings_cls = (
                ElevenLabsTTSSettings
                if provider == TTSProvider.ELEVENLABS
                else DeepgramTTSSettings
            )
            return TTSUpdateSettingsFrame(delta=settings_cls(voice=voice_id))

        if provider == TTSProvider.CARTESIA:
            settings_cls = CartesiaTTSSettings
            language = pipecat_language(lang_code, 'Cartesia')
        elif provider == TTSProvider.AZURE:
            settings_cls = AzureTTSSettings
            language = map_language(lang_code, AZURE_LANGUAGES, 'Azure TTS')
        elif provider == TTSProvider.SARVAM:
            settings_cls = SarvamTTSSettings
            language = map_language(lang_code, SARVAM_LANGUAGES, 'Sarvam TTS')
        else:
            logger.warning(
                f"TTS provider '{provider}' does not support runtime language updates"
            )
            return None

        delta: Dict[str, Any] = {}
        if voice_id:
            delta['voice'] = voice_id
        if language:
            delta['language'] = language
        if not delta:
            return None
        return TTSUpdateSettingsFrame(delta=settings_cls(**delta))


def _language_setting(parameters: Dict[str, Any], label: str) -> Dict[str, Any]:
    """``{'language': Language}`` for a stored language Pipecat recognises."""
    if 'language' not in parameters:
        return {}
    value = parameters['language']
    language = pipecat_language(value, label)
    # A non-string value is passed through as stored
    if language is None and isinstance(value, str):
        return {}
    return {'language': language}


def _create_elevenlabs_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
    model = parameters.get('model', 'eleven_flash_v2_5')
    settings = {
        'voice': voice_id,
        'model': model,
        **_language_setting(parameters, 'ElevenLabs'),
        **pick(
            parameters,
            ('stability', 'similarity_boost', 'style', 'use_speaker_boost', 'speed'),
        ),
    }

    logger.info(
        f'ElevenLabs TTS config: model={model}, '
        f"stability={settings.get('stability', 'default')}"
    )

    return ElevenLabsTTSService(
        api_key=api_key,
        settings=ElevenLabsTTSSettings(**settings),
        text_filters=_text_filters(),
    )


def _create_deepgram_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
    kwargs = {
        'api_key': api_key,
        **pick(parameters, ('base_url', 'encoding', 'sample_rate')),
    }

    logger.info(f'Deepgram TTS config: voice={voice_id}')

    return DeepgramTTSService(
        **kwargs,
        settings=DeepgramTTSSettings(voice=voice_id),
        text_filters=_text_filters(),
    )


def _create_cartesia_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
    model = parameters.get('model', 'sonic-3.6')
    settings = {
        'voice': voice_id,
        'model': model,
        **_language_setting(parameters, 'Cartesia'),
    }

    logger.info(f'Cartesia TTS config: voice={voice_id}, model={model}')

    return CartesiaTTSService(
        api_key=api_key,
        settings=CartesiaTTSSettings(**settings),
        text_filters=_text_filters(),
    )


def _create_sarvam_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
    """Sarvam TTS (WebSocket-based streaming)"""
    model = parameters.get('model', 'bulbul:v4-flash')
    settings = {
        'voice': voice_id,
        'model': model,
        **pick(
            parameters,
            ('pitch', 'pace', 'loudness', 'enable_preprocessing', 'temperature'),
        ),
    }
    language = map_language(parameters.get('language'), SARVAM_LANGUAGES, 'Sarvam')
    if language:
        settings['language'] = language

    logger.info(f'Sarvam TTS config: voice={voice_id}, model={model}')

    return SarvamTTSService(
        api_key=api_key,
        sample_rate=parameters.get('sample_rate'),
        settings=SarvamTTSSettings(**settings),
        # Emoji check after markdown, so "**😊**" is judged on what is left
        text_filters=_text_filters(UnspeakableTextFilter()),
    )


def _create_azure_tts(
    api_key: str, voice_id: str, region: Optional[str], parameters: Dict[str, Any]
):
    if not region:
        raise ValueError("Azure TTS requires 'region' to be set in the TTS config")

    settings = {
        'voice': voice_id,
        **pick_truthy(
            parameters, ('style', 'style_degree', 'role', 'rate', 'pitch', 'volume')
        ),
    }
    language = map_language(parameters.get('language'), AZURE_LANGUAGES, 'Azure')
    if language:
        settings['language'] = language

    kwargs = {
        'api_key': api_key,
        'region': region,
        **pick_truthy(parameters, ('sample_rate',)),
    }

    logger.info(f'Azure TTS config: voice={voice_id}, region={region}')

    return AzureTTSService(
        **kwargs, settings=AzureTTSSettings(**settings), text_filters=_text_filters()
    )


_CREATORS = {
    TTSProvider.ELEVENLABS: _create_elevenlabs_tts,
    TTSProvider.DEEPGRAM: _create_deepgram_tts,
    TTSProvider.CARTESIA: _create_cartesia_tts,
    TTSProvider.SARVAM: _create_sarvam_tts,
}
