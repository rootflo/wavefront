"""Cache key generation utilities for voice agent configurations"""

from uuid import UUID


def get_voice_agent_cache_key(agent_id: UUID) -> str:
    """Generate cache key for a voice agent"""
    return f'voice_agent:{agent_id}'


def get_llm_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for an LLM config"""
    return f'llm_inference_config:{config_id}'


def get_tts_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for a TTS config"""
    return f'tts_config:{config_id}'


def get_stt_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for an STT config"""
    return f'stt_config:{config_id}'


def get_telephony_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for a telephony config"""
    return f'telephony_config:{config_id}'


def get_tools_config_cache_key(agent_id: UUID) -> str:
    """Generate cache key for voice agent tools"""
    return f'voice_agent:{agent_id}:tools'
