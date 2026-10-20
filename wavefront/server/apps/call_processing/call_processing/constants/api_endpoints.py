"""API endpoint constants for floware config APIs"""

# Floware config API endpoints
VOICE_AGENT_ENDPOINT = '/floware/v1/voice-agents/{agent_id}'
LLM_INFERENCE_CONFIG_ENDPOINT = '/floware/v1/llm-inference-configs/{config_id}'
TTS_CONFIG_ENDPOINT = '/floware/v1/tts-configs/{config_id}'
STT_CONFIG_ENDPOINT = '/floware/v1/stt-configs/{config_id}'
TELEPHONY_CONFIG_ENDPOINT = '/floware/v1/telephony-configs/{config_id}'

# Config type mapping for cache invalidation
CONFIG_TYPE_ENDPOINTS = {
    'voice_agent': VOICE_AGENT_ENDPOINT,
    'llm_inference_config': LLM_INFERENCE_CONFIG_ENDPOINT,
    'tts_config': TTS_CONFIG_ENDPOINT,
    'stt_config': STT_CONFIG_ENDPOINT,
    'telephony_config': TELEPHONY_CONFIG_ENDPOINT,
}

# Valid config types
VALID_CONFIG_TYPES = set(CONFIG_TYPE_ENDPOINTS.keys())
