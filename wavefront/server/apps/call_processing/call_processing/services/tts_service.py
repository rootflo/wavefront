"""
TTS (Text-to-Speech) service factory

Supports multiple providers: ElevenLabs, Deepgram, Cartesia, Azure, Google, AWS
"""

from typing import Dict, Any
from call_processing.log.logger import logger

# Pipecat TTS services
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.sarvam.tts import SarvamTTSService

# Language for params
from pipecat.transcriptions.language import Language

# Add more as needed:
# from pipecat.services.azure.tts import AzureTTSService
# from pipecat.services.google.tts import GoogleTTSService


class TTSServiceFactory:
    """Factory for creating TTS service instances from configuration"""

    @staticmethod
    def create_tts_service(tts_config: Dict[str, Any]):
        """
        Create TTS service from configuration

        Args:
            tts_config: {
                'provider': 'elevenlabs' | 'deepgram' | 'cartesia' | 'azure' | 'google' | 'aws',
                'api_key': 'key',
                'voice_id': 'voice_id',
                'parameters': {
                    'model': 'model_name',
                    'stability': 0.5,
                    'similarity_boost': 0.75,
                    ...
                }
            }

        Returns:
            Pipecat TTS service instance
        """
        provider = tts_config['provider']
        api_key = tts_config['api_key']
        voice_id = tts_config['voice_id']
        parameters = tts_config.get('parameters', {})

        if parameters is None:
            parameters = {}

        logger.info(f'Creating TTS service: {provider} / voice: {voice_id}')

        if provider == 'elevenlabs':
            return TTSServiceFactory._create_elevenlabs_tts(
                api_key, voice_id, parameters
            )
        elif provider == 'deepgram':
            return TTSServiceFactory._create_deepgram_tts(api_key, voice_id, parameters)
        elif provider == 'cartesia':
            return TTSServiceFactory._create_cartesia_tts(api_key, voice_id, parameters)
        elif provider == 'sarvam':
            return TTSServiceFactory._create_sarvam_tts(api_key, voice_id, parameters)
        else:
            raise ValueError(f'Unsupported TTS provider: {provider}')

    @staticmethod
    def _create_elevenlabs_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
        """Create ElevenLabs TTS service"""
        # Model is a direct parameter, not in InputParams
        model = parameters.get('model', 'eleven_turbo_v2_5')

        # Build InputParams from the parameters dict
        params_dict = {}

        if 'language' in parameters:
            # Convert string to Language enum if needed
            lang = parameters['language']
            if isinstance(lang, str):
                try:
                    params_dict['language'] = Language(lang)
                except ValueError:
                    logger.warning(f"Unknown language '{lang}', skipping")
            else:
                params_dict['language'] = lang

        if 'stability' in parameters:
            params_dict['stability'] = parameters['stability']
        if 'similarity_boost' in parameters:
            params_dict['similarity_boost'] = parameters['similarity_boost']
        if 'style' in parameters:
            params_dict['style'] = parameters['style']
        if 'use_speaker_boost' in parameters:
            params_dict['use_speaker_boost'] = parameters['use_speaker_boost']
        if 'speed' in parameters:
            params_dict['speed'] = parameters['speed']

        # Create InputParams object (only if we have params)
        input_params = (
            ElevenLabsTTSService.InputParams(**params_dict) if params_dict else None
        )

        logger.info(
            f"ElevenLabs TTS config: model={model}, "
            f"stability={params_dict.get('stability', 'default')}"
        )

        return ElevenLabsTTSService(
            api_key=api_key, voice_id=voice_id, model=model, params=input_params
        )

    @staticmethod
    def _create_deepgram_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
        """Create Deepgram TTS service"""
        kwargs = {
            'api_key': api_key,
            'voice': voice_id,  # voice_id IS the model (e.g., "aura-2-helena-en")
        }

        # Optional parameters
        if 'base_url' in parameters:
            kwargs['base_url'] = parameters['base_url']
        if 'encoding' in parameters:
            kwargs['encoding'] = parameters['encoding']
        if 'sample_rate' in parameters:
            kwargs['sample_rate'] = parameters['sample_rate']

        logger.info(f'Deepgram TTS config: voice={voice_id}')
        return DeepgramTTSService(**kwargs)

    @staticmethod
    def _create_cartesia_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
        """Create Cartesia TTS service"""
        # Model is a direct parameter
        model = parameters.get('model', 'sonic-2')

        # Build InputParams from the parameters dict
        params_dict = {}

        if 'language' in parameters:
            # Convert string to Language enum if needed
            lang = parameters['language']
            if isinstance(lang, str):
                try:
                    params_dict['language'] = Language(lang)
                except ValueError:
                    logger.warning(f"Unknown language '{lang}', skipping")
            else:
                params_dict['language'] = lang

        if 'speed' in parameters:
            params_dict['speed'] = parameters['speed']

        # Create InputParams object (only if we have params)
        input_params = (
            CartesiaTTSService.InputParams(**params_dict) if params_dict else None
        )

        logger.info(f'Cartesia TTS config: voice={voice_id}, model={model}')

        return CartesiaTTSService(
            api_key=api_key, voice_id=voice_id, model=model, params=input_params
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
    def _create_sarvam_tts(api_key: str, voice_id: str, parameters: Dict[str, Any]):
        """Create Sarvam TTS service (WebSocket-based streaming)"""
        model = parameters.get('model', 'bulbul:v2')

        # Build InputParams from the parameters dict
        params_dict = {}

        if 'language' in parameters and parameters['language']:
            lang_code = parameters['language']
            lang_enum = TTSServiceFactory.SARVAM_LANGUAGE_MAP.get(lang_code)
            if lang_enum:
                params_dict['language'] = lang_enum
            else:
                logger.warning(f"Unknown Sarvam language '{lang_code}', skipping")

        if 'pitch' in parameters:
            params_dict['pitch'] = parameters['pitch']
        if 'pace' in parameters:
            params_dict['pace'] = parameters['pace']
        if 'loudness' in parameters:
            params_dict['loudness'] = parameters['loudness']
        if 'enable_preprocessing' in parameters:
            params_dict['enable_preprocessing'] = parameters['enable_preprocessing']
        if 'temperature' in parameters:
            params_dict['temperature'] = parameters['temperature']

        input_params = (
            SarvamTTSService.InputParams(**params_dict) if params_dict else None
        )

        logger.info(f'Sarvam TTS config: voice={voice_id}, model={model}')

        return SarvamTTSService(
            api_key=api_key, voice_id=voice_id, model=model, params=input_params
        )
