"""
STT (Speech-to-Text) service factory

Supports Deepgram, Sarvam, ElevenLabs and Azure.
"""

from typing import Any, Dict, Optional

from pipecat.frames.frames import STTUpdateSettingsFrame
from pipecat.services.azure.stt import AzureSTTService, AzureSTTSettings
from pipecat.services.deepgram.stt import DeepgramSTTService, DeepgramSTTSettings
from pipecat.services.elevenlabs.stt import (
    ElevenLabsRealtimeSTTService,
    ElevenLabsRealtimeSTTSettings,
)
from pipecat.services.sarvam.stt import SarvamSTTService, SarvamSTTSettings

from call_processing.log.logger import logger
from call_processing.services.common.providers.provider_types import STTProvider
from call_processing.services.common.providers.provider_utils import (
    AZURE_LANGUAGES,
    ELEVENLABS_STT_LANGUAGES,
    SARVAM_LANGUAGES,
    map_language,
    pick,
    pick_truthy,
)

# Telephony audio; WebRTC callers pass their own rate in ``parameters``
DEFAULT_SAMPLE_RATE = 8000

NOT_IMPLEMENTED_PROVIDERS = {
    STTProvider.ASSEMBLYAI: 'AssemblyAI',
    STTProvider.WHISPER: 'Whisper',
}


class STTServiceFactory:
    """Factory for creating STT service instances from configuration"""

    @staticmethod
    def create_stt_service(stt_config: Dict[str, Any]):
        """Build a Pipecat STT service from a stored STT config.

        Reads ``provider`` (an ``STTProvider``), ``api_key``, ``region`` (Azure
        only) and provider ``parameters`` such as ``model`` and ``language``.
        """
        provider = stt_config['provider']
        api_key = stt_config['api_key']
        parameters = stt_config.get('parameters') or {}

        logger.info(f'Creating STT service: {provider}')

        if provider == STTProvider.AZURE:
            return _create_azure_stt(api_key, stt_config.get('region'), parameters)
        create = _CREATORS.get(provider)
        if create is not None:
            return create(api_key, parameters)
        if provider in NOT_IMPLEMENTED_PROVIDERS:
            raise NotImplementedError(
                f'{NOT_IMPLEMENTED_PROVIDERS[provider]} STT provider not yet implemented'
            )
        raise ValueError(f'Unsupported STT provider: {provider}')

    @staticmethod
    def create_language_update_frame(
        provider: str, lang_code: str
    ) -> Optional[STTUpdateSettingsFrame]:
        """Create STTUpdateSettingsFrame for a runtime language switch, provider-aware."""
        if provider == STTProvider.DEEPGRAM:
            return STTUpdateSettingsFrame(delta=DeepgramSTTSettings(language=lang_code))

        mapping = _LANGUAGE_UPDATES.get(provider)
        if mapping is None:
            logger.warning(
                f"STT provider '{provider}' does not support runtime language updates"
            )
            return None
        languages, settings_cls, label = mapping
        language = map_language(lang_code, languages, label)
        if language is None:
            return None
        return STTUpdateSettingsFrame(delta=settings_cls(language=language))


def _create_deepgram_stt(api_key: str, parameters: Dict[str, Any]):
    # Runtime-updatable settings
    settings = {
        'model': parameters.get('model', 'nova-3-general'),
        'interim_results': parameters.get('interim_results', True),
        **pick(
            parameters, ('language', 'smart_format', 'punctuate', 'profanity_filter')
        ),
    }

    # Init-level params (not runtime-updatable)
    kwargs = {
        'api_key': api_key,
        'encoding': parameters.get('encoding', 'linear16'),
        'sample_rate': parameters.get('sample_rate', DEFAULT_SAMPLE_RATE),
        **pick(parameters, ('channels',)),
        # e.g. 'api.eu.deepgram.com' for EU-region projects; scheme optional
        **pick_truthy(parameters, ('base_url',)),
    }

    logger.info(f"Deepgram STT config: model={settings['model']}")

    return DeepgramSTTService(**kwargs, settings=DeepgramSTTSettings(**settings))


def _create_sarvam_stt(api_key: str, parameters: Dict[str, Any]):
    model = parameters.get('model', 'saaras:v4')
    sample_rate = parameters.get('sample_rate', DEFAULT_SAMPLE_RATE)
    settings = {
        'model': model,
        **pick(parameters, ('vad_signals', 'high_vad_sensitivity')),
    }
    language = map_language(parameters.get('language'), SARVAM_LANGUAGES, 'Sarvam')
    if language:
        settings['language'] = language

    logger.info(f'Sarvam STT config: model={model}, sample_rate={sample_rate}')

    return SarvamSTTService(
        api_key=api_key,
        sample_rate=sample_rate,
        settings=SarvamSTTSettings(**settings),
    )


def _create_elevenlabs_stt(api_key: str, parameters: Dict[str, Any]):
    """ElevenLabs Realtime STT (WebSocket streaming, scribe_v2_realtime)"""
    model = parameters.get('model', 'scribe_v2_realtime')
    sample_rate = parameters.get('sample_rate', DEFAULT_SAMPLE_RATE)
    settings: Dict[str, Any] = {'model': model}
    # An unmapped language leaves ElevenLabs to auto-detect
    language = map_language(
        parameters.get('language'), ELEVENLABS_STT_LANGUAGES, 'ElevenLabs'
    )
    if language:
        settings['language'] = language

    logger.info(f'ElevenLabs STT config: model={model}, sample_rate={sample_rate}')

    return ElevenLabsRealtimeSTTService(
        api_key=api_key,
        sample_rate=sample_rate,
        settings=ElevenLabsRealtimeSTTSettings(**settings),
    )


def _create_azure_stt(api_key: str, region: Optional[str], parameters: Dict[str, Any]):
    if not region:
        raise ValueError("Azure STT requires 'region' to be set in the STT config")

    kwargs = {
        'api_key': api_key,
        'region': region,
        **pick_truthy(parameters, ('sample_rate', 'endpoint_id')),
    }
    if parameters.get('ttfs_p99_latency') is not None:
        kwargs['ttfs_p99_latency'] = parameters['ttfs_p99_latency']

    language = map_language(parameters.get('language'), AZURE_LANGUAGES, 'Azure')

    logger.info(f'Azure STT config: region={region}')

    return AzureSTTService(
        **kwargs,
        settings=AzureSTTSettings(language=language) if language else None,
    )


_CREATORS = {
    STTProvider.DEEPGRAM: _create_deepgram_stt,
    STTProvider.SARVAM: _create_sarvam_stt,
    STTProvider.ELEVENLABS: _create_elevenlabs_stt,
}

# provider -> (language map, Settings class, label for warnings)
_LANGUAGE_UPDATES = {
    STTProvider.AZURE: (AZURE_LANGUAGES, AzureSTTSettings, 'Azure STT'),
    STTProvider.SARVAM: (SARVAM_LANGUAGES, SarvamSTTSettings, 'Sarvam STT'),
    STTProvider.ELEVENLABS: (
        ELEVENLABS_STT_LANGUAGES,
        ElevenLabsRealtimeSTTSettings,
        'ElevenLabs STT',
    ),
}
