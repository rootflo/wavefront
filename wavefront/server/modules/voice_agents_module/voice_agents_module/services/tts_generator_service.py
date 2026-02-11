"""
TTS Generator Service

Generates audio from text using various TTS providers.
This service is used to pre-generate welcome message audio files.
"""

import base64
import httpx
from typing import Dict, Any
from common_module.log.logger import logger


class TTSGeneratorService:
    """Service to generate audio from text using TTS providers"""

    def __init__(self):
        self.timeout = 30.0  # 30 seconds timeout for API calls

    async def generate_audio(self, text: str, tts_config: Dict[str, Any]) -> bytes:
        """
        Generate audio from text using the specified TTS configuration.

        Args:
            text: Text to convert to speech
            tts_config: TTS configuration dict with provider, api_key, voice_id, parameters

        Returns:
            bytes: Audio data in MP3 format

        Raises:
            ValueError: If provider is not supported
            Exception: If TTS generation fails
        """
        provider = tts_config.get('provider')
        api_key = tts_config.get('api_key')
        voice_id = tts_config.get('voice_id')
        parameters = tts_config.get('parameters', {}) or {}

        logger.info(f'Generating audio with {provider} for voice {voice_id}')

        if provider == 'elevenlabs':
            return await self._generate_elevenlabs(text, api_key, voice_id, parameters)
        elif provider == 'deepgram':
            return await self._generate_deepgram(text, api_key, voice_id, parameters)
        elif provider == 'cartesia':
            return await self._generate_cartesia(text, api_key, voice_id, parameters)
        elif provider == 'sarvam':
            return await self._generate_sarvam(text, api_key, voice_id, parameters)
        else:
            raise ValueError(
                f'Unsupported TTS provider for audio generation: {provider}'
            )

    async def _generate_elevenlabs(
        self, text: str, api_key: str, voice_id: str, parameters: Dict[str, Any]
    ) -> bytes:
        """
        Generate audio using ElevenLabs API.

        API Docs: https://elevenlabs.io/docs/api-reference/text-to-speech
        """
        url = f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}'

        headers = {
            'xi-api-key': api_key,
            'Content-Type': 'application/json',
        }

        # Build request body with voice settings
        body = {
            'text': text,
            'model_id': parameters.get('model', 'eleven_multilingual_v2'),
        }

        # Add voice settings if specified
        voice_settings = {}
        if 'stability' in parameters:
            voice_settings['stability'] = parameters['stability']
        if 'similarity_boost' in parameters:
            voice_settings['similarity_boost'] = parameters['similarity_boost']
        if 'style' in parameters:
            voice_settings['style'] = parameters['style']
        if 'use_speaker_boost' in parameters:
            voice_settings['use_speaker_boost'] = parameters['use_speaker_boost']
        if 'speed' in parameters:
            voice_settings['speed'] = parameters['speed']

        if voice_settings:
            body['voice_settings'] = voice_settings

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()

                # ElevenLabs returns audio directly
                logger.info(
                    f'ElevenLabs audio generated successfully, size: {len(response.content)} bytes'
                )
                return response.content

        except httpx.HTTPStatusError as e:
            logger.error(
                f'ElevenLabs API error: {e.response.status_code} - {e.response.text}'
            )
            raise Exception(f'ElevenLabs TTS generation failed: {e.response.text}')
        except Exception as e:
            logger.error(f'ElevenLabs request failed: {str(e)}')
            raise Exception(f'ElevenLabs TTS generation failed: {str(e)}')

    async def _generate_deepgram(
        self, text: str, api_key: str, voice_id: str, parameters: Dict[str, Any]
    ) -> bytes:
        """
        Generate audio using Deepgram API.

        API Docs: https://developers.deepgram.com/docs/text-to-speech
        """
        base_url = parameters.get('base_url', 'https://api.deepgram.com')
        url = f'{base_url}/v1/speak'

        headers = {
            'Authorization': f'Token {api_key}',
            'Content-Type': 'application/json',
        }

        # Build query parameters
        params = {
            'model': voice_id,  # voice_id is the model (e.g., "aura-2-helena-en")
        }

        if 'encoding' in parameters:
            params['encoding'] = parameters['encoding']
        else:
            params['encoding'] = 'mp3'  # Default to mp3

        if 'sample_rate' in parameters:
            params['sample_rate'] = parameters['sample_rate']

        body = {'text': text}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url, headers=headers, params=params, json=body
                )
                response.raise_for_status()

                logger.info(
                    f'Deepgram audio generated successfully, size: {len(response.content)} bytes'
                )
                return response.content

        except httpx.HTTPStatusError as e:
            logger.error(
                f'Deepgram API error: {e.response.status_code} - {e.response.text}'
            )
            raise Exception(f'Deepgram TTS generation failed: {e.response.text}')
        except Exception as e:
            logger.error(f'Deepgram request failed: {str(e)}')
            raise Exception(f'Deepgram TTS generation failed: {str(e)}')

    async def _generate_cartesia(
        self, text: str, api_key: str, voice_id: str, parameters: Dict[str, Any]
    ) -> bytes:
        """
        Generate audio using Cartesia API.

        API Docs: https://docs.cartesia.ai/api-reference/tts/bytes
        """
        url = 'https://api.cartesia.ai/tts/bytes'

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Cartesia-Version': '2025-04-16',
            'Content-Type': 'application/json',
        }

        # Build request body
        body = {
            'model_id': parameters.get('model', 'sonic-3'),
            'transcript': text,
            'voice': {
                'mode': 'id',
                'id': voice_id,
            },
            'output_format': {
                'container': 'mp3',
                'sample_rate': parameters.get(
                    'sample_rate', 44100
                ),  # 8000, 16000, 22050, 24000, 44100, 48000
                'bit_rate': parameters.get(
                    'bit_rate', 128000
                ),  # 32000, 64000, 96000, 128000, 192000
            },
        }

        # Add language (default to 'en')
        body['language'] = parameters.get('language', 'en')

        # Build generation_config if any parameters are specified
        generation_config = {}
        if 'volume' in parameters:
            generation_config['volume'] = parameters['volume']
        if 'speed' in parameters:
            generation_config['speed'] = parameters['speed']
        if 'emotion' in parameters:
            generation_config['emotion'] = parameters['emotion']

        if generation_config:
            body['generation_config'] = generation_config

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()

                logger.info(
                    f'Cartesia audio generated successfully, size: {len(response.content)} bytes'
                )
                return response.content

        except httpx.HTTPStatusError as e:
            logger.error(
                f'Cartesia API error: {e.response.status_code} - {e.response.text}'
            )
            raise Exception(f'Cartesia TTS generation failed: {e.response.text}')
        except Exception as e:
            logger.error(f'Cartesia request failed: {str(e)}')
            raise Exception(f'Cartesia TTS generation failed: {str(e)}')

    # Mapping of short language codes to Sarvam API format
    SARVAM_LANGUAGE_CODE_MAP = {
        'bn': 'bn-IN',
        'en': 'en-IN',
        'gu': 'gu-IN',
        'hi': 'hi-IN',
        'kn': 'kn-IN',
        'ml': 'ml-IN',
        'mr': 'mr-IN',
        'or': 'od-IN',
        'pa': 'pa-IN',
        'ta': 'ta-IN',
        'te': 'te-IN',
    }

    async def _generate_sarvam(
        self, text: str, api_key: str, voice_id: str, parameters: Dict[str, Any]
    ) -> bytes:
        """
        Generate audio using Sarvam AI REST API.

        API Docs: https://docs.sarvam.ai/api-reference-docs/endpoints/text-to-speech
        """
        url = 'https://api.sarvam.ai/text-to-speech'

        headers = {
            'api-subscription-key': api_key,
            'Content-Type': 'application/json',
        }

        # Map short language code to Sarvam format
        lang = parameters.get('language', 'hi')
        target_language_code = self.SARVAM_LANGUAGE_CODE_MAP.get(lang, f'{lang}-IN')

        body = {
            'text': text,
            'target_language_code': target_language_code,
            'speaker': voice_id,
            'model': parameters.get('model', 'bulbul:v2'),
        }

        # Optional parameters
        if 'pitch' in parameters:
            body['pitch'] = parameters['pitch']
        if 'pace' in parameters:
            body['pace'] = parameters['pace']
        if 'loudness' in parameters:
            body['loudness'] = parameters['loudness']
        if 'sample_rate' in parameters:
            body['sample_rate'] = parameters['sample_rate']
        if 'enable_preprocessing' in parameters:
            body['enable_preprocessing'] = parameters['enable_preprocessing']

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()

                # Sarvam returns JSON with audios[] array of base64-encoded audio
                data = response.json()
                audios = data.get('audios')
                if not audios:
                    raise ValueError(f'Sarvam API returned no audio data: {data}')
                audio_b64 = audios[0]
                audio_bytes = base64.b64decode(audio_b64)

                logger.info(
                    f'Sarvam audio generated successfully, size: {len(audio_bytes)} bytes'
                )
                return audio_bytes

        except httpx.HTTPStatusError as e:
            logger.error(
                f'Sarvam API error: {e.response.status_code} - {e.response.text}'
            )
            raise Exception(f'Sarvam TTS generation failed: {e.response.text}')
        except Exception as e:
            logger.error(f'Sarvam request failed: {str(e)}')
            raise Exception(f'Sarvam TTS generation failed: {str(e)}')
