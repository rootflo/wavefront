"""
STT (Speech-to-Text) service factory

Supports multiple providers: Deepgram, Sarvam, ElevenLabs
"""

from typing import Dict, Any
from call_processing.log.logger import logger

# Pipecat STT services and their Settings classes
from pipecat.services.deepgram.stt import DeepgramSTTService, DeepgramSTTSettings
from pipecat.services.sarvam.stt import SarvamSTTService, SarvamSTTSettings
from pipecat.services.elevenlabs.stt import (
    ElevenLabsRealtimeSTTService,
    ElevenLabsRealtimeSTTSettings,
)
from pipecat.services.azure.stt import AzureSTTService, AzureSTTSettings

# Pipecat language enum
from pipecat.transcriptions.language import Language

# Frames
from pipecat.frames.frames import STTUpdateSettingsFrame


class STTServiceFactory:
    """Factory for creating STT service instances from configuration"""

    @staticmethod
    def create_stt_service(stt_config: Dict[str, Any]):
        """
        Create STT service from configuration

        Args:
            stt_config: {
                'provider': 'deepgram' | 'assemblyai' | 'whisper' | 'google' | 'azure',
                'api_key': 'key',
                'parameters': {
                    'model': 'nova-2',
                    'language': 'en',
                    ...
                }
            }

        Returns:
            Pipecat STT service instance
        """
        provider = stt_config['provider']
        api_key = stt_config['api_key']
        region = stt_config.get('region')
        parameters = stt_config.get('parameters', {})

        if parameters is None:
            parameters = {}

        logger.info(f'Creating STT service: {provider}')

        if provider == 'deepgram':
            return STTServiceFactory._create_deepgram_stt(api_key, parameters)
        elif provider == 'sarvam':
            return STTServiceFactory._create_sarvam_stt(api_key, parameters)
        elif provider == 'elevenlabs':
            return STTServiceFactory._create_elevenlabs_stt(api_key, parameters)
        elif provider == 'azure':
            return STTServiceFactory._create_azure_stt(api_key, region, parameters)
        elif provider == 'assemblyai':
            return STTServiceFactory._create_assemblyai_stt(api_key, parameters)
        elif provider == 'whisper':
            return STTServiceFactory._create_whisper_stt(api_key, parameters)
        else:
            raise ValueError(f'Unsupported STT provider: {provider}')

    @staticmethod
    def _create_deepgram_stt(api_key: str, parameters: Dict[str, Any]):
        """Create Deepgram STT service"""
        # Runtime-updatable settings
        settings_kwargs: Dict[str, Any] = {
            'model': parameters.get('model', 'nova-2'),
            'interim_results': parameters.get('interim_results', True),
        }

        if 'language' in parameters:
            settings_kwargs['language'] = parameters['language']
        if 'smart_format' in parameters:
            settings_kwargs['smart_format'] = parameters['smart_format']
        if 'punctuate' in parameters:
            settings_kwargs['punctuate'] = parameters['punctuate']
        if 'profanity_filter' in parameters:
            settings_kwargs['profanity_filter'] = parameters['profanity_filter']

        # Init-level params (not runtime-updatable)
        kwargs: Dict[str, Any] = {
            'api_key': api_key,
            'encoding': parameters.get('encoding', 'linear16'),
        }
        if 'sample_rate' in parameters:
            kwargs['sample_rate'] = parameters['sample_rate']
        else:
            kwargs['sample_rate'] = 8000
        if 'channels' in parameters:
            kwargs['channels'] = parameters['channels']

        logger.info(f"Deepgram STT config: model={settings_kwargs['model']}")

        return DeepgramSTTService(
            **kwargs,
            settings=DeepgramSTTSettings(**settings_kwargs),
        )

    # Mapping of short language codes to pipecat Language enum for Sarvam
    SARVAM_LANGUAGE_MAP = {
        'bn': Language.BN_IN,
        'en': Language.EN_IN,
        'gu': Language.GU_IN,
        'hi': Language.HI_IN,
        'kn': Language.KN_IN,
        'ml': Language.ML_IN,
        'mr': Language.MR_IN,
        'or': Language.OR_IN,
        'pa': Language.PA_IN,
        'ta': Language.TA_IN,
        'te': Language.TE_IN,
    }

    @staticmethod
    def _create_sarvam_stt(api_key: str, parameters: Dict[str, Any]):
        """Create Sarvam STT service"""
        settings_kwargs: Dict[str, Any] = {}

        if 'language' in parameters and parameters['language']:
            lang_code = parameters['language']
            lang_enum = STTServiceFactory.SARVAM_LANGUAGE_MAP.get(lang_code)
            if lang_enum:
                settings_kwargs['language'] = lang_enum
            else:
                logger.warning(f"Unknown Sarvam language '{lang_code}', skipping")

        if 'vad_signals' in parameters:
            settings_kwargs['vad_signals'] = parameters['vad_signals']
        if 'high_vad_sensitivity' in parameters:
            settings_kwargs['high_vad_sensitivity'] = parameters['high_vad_sensitivity']

        model = parameters.get('model', 'saarika:v2.5')
        sample_rate = parameters.get('sample_rate', 8000)

        logger.info(f'Sarvam STT config: model={model}, sample_rate={sample_rate}')

        return SarvamSTTService(
            api_key=api_key,
            model=model,
            sample_rate=sample_rate,
            settings=SarvamSTTSettings(**settings_kwargs) if settings_kwargs else None,
        )

    # Mapping of short language codes to ElevenLabs ISO-639-3 language codes
    ELEVENLABS_LANGUAGE_MAP = {
        'en': 'eng',
        'hi': 'hin',
        'ta': 'tam',
        'te': 'tel',
        'kn': 'kan',
        'ml': 'mal',
        'gu': 'guj',
        'bn': 'ben',
        'mr': 'mar',
        'pa': 'pan',
        'or': 'ori',
    }

    AZURE_LANGUAGE_MAP = {
        'en': Language.EN_US,
        'hi': Language.HI_IN,
        'ta': Language.TA_IN,
        'te': Language.TE_IN,
        'kn': Language.KN_IN,
        'ml': Language.ML_IN,
        'gu': Language.GU_IN,
        'bn': Language.BN_IN,
        'mr': Language.MR_IN,
        'pa': Language.PA_IN,
        'or': Language.OR_IN,
    }

    @staticmethod
    def _create_elevenlabs_stt(api_key: str, parameters: Dict[str, Any]):
        """Create ElevenLabs Realtime STT service (WebSocket streaming, scribe_v2_realtime)"""
        settings_kwargs: Dict[str, Any] = {}

        if 'language' in parameters and parameters['language']:
            lang_code = parameters['language']
            lang_code_iso = STTServiceFactory.ELEVENLABS_LANGUAGE_MAP.get(lang_code)
            if lang_code_iso:
                settings_kwargs['language'] = lang_code_iso
            else:
                logger.warning(
                    f"Unknown ElevenLabs language '{lang_code}', skipping (auto-detect will be used)"
                )

        model = parameters.get('model', 'scribe_v2_realtime')
        sample_rate = parameters.get('sample_rate', 8000)

        logger.info(f'ElevenLabs STT config: model={model}, sample_rate={sample_rate}')

        return ElevenLabsRealtimeSTTService(
            api_key=api_key,
            model=model,
            sample_rate=sample_rate,
            settings=ElevenLabsRealtimeSTTSettings(**settings_kwargs)
            if settings_kwargs
            else None,
        )

    @staticmethod
    def _create_azure_stt(api_key: str, region: str, parameters: Dict[str, Any]):
        """Create Azure STT service"""
        if not region:
            raise ValueError("Azure STT requires 'region' to be set in the STT config")

        kwargs: Dict[str, Any] = {
            'api_key': api_key,
            'region': region,
        }

        if 'sample_rate' in parameters and parameters['sample_rate']:
            kwargs['sample_rate'] = parameters['sample_rate']
        if 'endpoint_id' in parameters and parameters['endpoint_id']:
            kwargs['endpoint_id'] = parameters['endpoint_id']
        if (
            'ttfs_p99_latency' in parameters
            and parameters['ttfs_p99_latency'] is not None
        ):
            kwargs['ttfs_p99_latency'] = parameters['ttfs_p99_latency']

        settings_kwargs: Dict[str, Any] = {}
        if 'language' in parameters and parameters['language']:
            lang_code = parameters['language']
            lang_enum = STTServiceFactory.AZURE_LANGUAGE_MAP.get(lang_code)
            if lang_enum:
                settings_kwargs['language'] = lang_enum
            else:
                logger.warning(
                    f"Unknown Azure language '{lang_code}', using service default"
                )

        logger.info(f'Azure STT config: region={region}')

        return AzureSTTService(
            **kwargs,
            settings=AzureSTTSettings(**settings_kwargs) if settings_kwargs else None,
        )

    @staticmethod
    def create_language_update_frame(provider: str, lang_code: str):
        """Create STTUpdateSettingsFrame for a runtime language switch, provider-aware."""
        if provider == 'deepgram':
            return STTUpdateSettingsFrame(delta=DeepgramSTTSettings(language=lang_code))
        elif provider == 'azure':
            lang_enum = STTServiceFactory.AZURE_LANGUAGE_MAP.get(lang_code)
            if not lang_enum:
                logger.warning(f"No Azure STT language mapping for '{lang_code}'")
                return None
            return STTUpdateSettingsFrame(delta=AzureSTTSettings(language=lang_enum))
        elif provider == 'sarvam':
            lang_enum = STTServiceFactory.SARVAM_LANGUAGE_MAP.get(lang_code)
            if not lang_enum:
                logger.warning(f"No Sarvam STT language mapping for '{lang_code}'")
                return None
            return STTUpdateSettingsFrame(delta=SarvamSTTSettings(language=lang_enum))
        elif provider == 'elevenlabs':
            lang_code_iso = STTServiceFactory.ELEVENLABS_LANGUAGE_MAP.get(lang_code)
            if not lang_code_iso:
                logger.warning(f"No ElevenLabs STT language mapping for '{lang_code}'")
                return None
            return STTUpdateSettingsFrame(
                delta=ElevenLabsRealtimeSTTSettings(language=lang_code_iso)
            )
        else:
            logger.warning(
                f"STT provider '{provider}' does not support runtime language updates"
            )
            return None

    @staticmethod
    def _create_assemblyai_stt(api_key: str, parameters: Dict[str, Any]):
        """Create AssemblyAI STT service"""
        # TODO: Implement AssemblyAI
        raise NotImplementedError('AssemblyAI STT provider not yet implemented')

    @staticmethod
    def _create_whisper_stt(api_key: str, parameters: Dict[str, Any]):
        """Create Whisper STT service"""
        # TODO: Implement Whisper
        raise NotImplementedError('Whisper STT provider not yet implemented')
