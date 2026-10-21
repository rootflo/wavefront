"""The browser (WebRTC) path must run STT/TTS at 16 kHz, never the 8 kHz telephony defaults."""

from call_processing.services.audio_config import (
    TELEPHONY_SAMPLE_RATE,
    service_sample_rate,
    with_sample_rate,
)
from call_processing.services.stt_service import STTServiceFactory
from call_processing.services.tts_service import TTSServiceFactory

WEBRTC_RATE = 16000


def _stt_config(provider: str, **parameters):
    return {
        'provider': provider,
        'api_key': 'test-key',
        'region': 'eastus',
        'parameters': parameters,
    }


def _tts_config(provider: str, **parameters):
    return {
        'provider': provider,
        'api_key': 'test-key',
        'region': 'eastus',
        'voice_id': 'voice',
        'parameters': parameters,
    }


def test_only_webrtc_forces_a_service_rate():
    assert service_sample_rate('webrtc', WEBRTC_RATE) == WEBRTC_RATE
    for telephony in ('twilio', 'exotel', 'smartflo'):
        assert service_sample_rate(telephony, TELEPHONY_SAMPLE_RATE) is None


def test_with_sample_rate_overrides_agent_parameters_without_mutating_input():
    original = _stt_config('deepgram', sample_rate=8000, model='nova-2')

    forced = with_sample_rate(original, WEBRTC_RATE)

    assert forced['parameters']['sample_rate'] == WEBRTC_RATE
    assert forced['parameters']['model'] == 'nova-2'
    assert original['parameters']['sample_rate'] == 8000


def test_with_sample_rate_none_keeps_telephony_config():
    original = _stt_config('deepgram')
    assert with_sample_rate(original, None) is original


def test_telephony_stt_defaults_stay_at_8k():
    for provider in ('deepgram', 'sarvam', 'elevenlabs'):
        service = STTServiceFactory.create_stt_service(_stt_config(provider))
        assert service._init_sample_rate == TELEPHONY_SAMPLE_RATE, provider


def test_webrtc_stt_services_get_16k_even_when_agent_stored_8k():
    for provider in ('deepgram', 'sarvam', 'elevenlabs', 'azure'):
        config = with_sample_rate(
            _stt_config(provider, sample_rate=TELEPHONY_SAMPLE_RATE), WEBRTC_RATE
        )
        service = STTServiceFactory.create_stt_service(config)
        assert service._init_sample_rate == WEBRTC_RATE, provider


def test_webrtc_tts_services_get_16k_or_follow_the_pipeline_rate():
    for provider in ('deepgram', 'sarvam', 'azure'):
        config = with_sample_rate(
            _tts_config(provider, sample_rate=TELEPHONY_SAMPLE_RATE), WEBRTC_RATE
        )
        service = TTSServiceFactory.create_tts_service(config)
        assert service._init_sample_rate == WEBRTC_RATE, provider

    # These take the rate from the pipeline (PipelineParams.audio_out_sample_rate),
    # so they must not pin an 8 kHz value of their own.
    for provider in ('elevenlabs', 'cartesia'):
        service = TTSServiceFactory.create_tts_service(
            with_sample_rate(_tts_config(provider), WEBRTC_RATE)
        )
        assert not service._init_sample_rate, provider
