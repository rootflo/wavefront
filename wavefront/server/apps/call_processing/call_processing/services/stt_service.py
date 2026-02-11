"""
STT (Speech-to-Text) service factory

Supports multiple providers: Deepgram, AssemblyAI, Whisper, Google, Azure
"""

from typing import Dict, Any
from call_processing.log.logger import logger

# Pipecat STT services
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.sarvam.stt import SarvamSTTService

# Pipecat language enum
from pipecat.transcriptions.language import Language

# Deepgram options
from deepgram import LiveOptions

# Add more as needed:
# from pipecat.services.assemblyai.stt import AssemblyAISTTService
# from pipecat.services.whisper.stt import WhisperSTTService


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
        parameters = stt_config.get('parameters', {})

        if parameters is None:
            parameters = {}

        logger.info(f'Creating STT service: {provider}')

        if provider == 'deepgram':
            return STTServiceFactory._create_deepgram_stt(api_key, parameters)
        elif provider == 'sarvam':
            return STTServiceFactory._create_sarvam_stt(api_key, parameters)
        elif provider == 'assemblyai':
            return STTServiceFactory._create_assemblyai_stt(api_key, parameters)
        elif provider == 'whisper':
            return STTServiceFactory._create_whisper_stt(api_key, parameters)
        else:
            raise ValueError(f'Unsupported STT provider: {provider}')

    @staticmethod
    def _create_deepgram_stt(api_key: str, parameters: Dict[str, Any]):
        """Create Deepgram STT service"""
        # Build LiveOptions from the parameters dict
        options_dict = {}

        # Add parameters from config
        if 'model' in parameters:
            options_dict['model'] = parameters['model']
        if 'language' in parameters:
            options_dict['language'] = parameters['language']
        if 'interim_results' in parameters:
            options_dict['interim_results'] = parameters['interim_results']
        if 'encoding' in parameters:
            options_dict['encoding'] = parameters['encoding']
        if 'sample_rate' in parameters:
            options_dict['sample_rate'] = parameters['sample_rate']
        # if 'endpointing' in parameters:   # using pipecat VAD + smart turn detection
        #     options_dict['endpointing'] = parameters['endpointing']
        if 'channels' in parameters:
            options_dict['channels'] = parameters['channels']
        if 'smart_format' in parameters:
            options_dict['smart_format'] = parameters['smart_format']
        if 'punctuate' in parameters:
            options_dict['punctuate'] = parameters['punctuate']
        if 'profanity_filter' in parameters:
            options_dict['profanity_filter'] = parameters['profanity_filter']
        # if 'vad_events' in parameters:    # depreceated in pipecat 0.99+
        #     options_dict['vad_events'] = parameters['vad_events']

        # Set smart defaults if not provided
        options_dict.setdefault(
            'interim_results', True
        )  # Always enable for faster feedback
        # options_dict.setdefault('endpointing', 300)  # 300ms = faster cutoff
        options_dict.setdefault('encoding', 'linear16')
        options_dict.setdefault('sample_rate', 8000)
        options_dict.setdefault('model', 'nova-2')

        # Create LiveOptions object
        live_options = LiveOptions(**options_dict)

        logger.info(
            f"Deepgram STT config: model={options_dict.get('model', 'default')}"
        )

        return DeepgramSTTService(api_key=api_key, live_options=live_options)

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
        params_dict = {}

        # Map language code to pipecat Language enum
        if 'language' in parameters and parameters['language']:
            lang_code = parameters['language']
            lang_enum = STTServiceFactory.SARVAM_LANGUAGE_MAP.get(lang_code)
            if lang_enum:
                params_dict['language'] = lang_enum
            else:
                logger.warning(f"Unknown Sarvam language '{lang_code}', skipping")

        if 'vad_signals' in parameters:
            params_dict['vad_signals'] = parameters['vad_signals']
        if 'high_vad_sensitivity' in parameters:
            params_dict['high_vad_sensitivity'] = parameters['high_vad_sensitivity']

        model = parameters.get('model', 'saarika:v2.5')
        sample_rate = parameters.get('sample_rate', 8000)

        input_params = (
            SarvamSTTService.InputParams(**params_dict) if params_dict else None
        )

        logger.info(f'Sarvam STT config: model={model}, sample_rate={sample_rate}')

        return SarvamSTTService(
            api_key=api_key,
            model=model,
            sample_rate=sample_rate,
            params=input_params,
        )

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
