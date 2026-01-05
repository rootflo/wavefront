from uuid import UUID


def get_telephony_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for a telephony config"""
    return f'telephony_config:{config_id}'


def get_telephony_configs_list_cache_key() -> str:
    """Generate cache key for telephony configs list"""
    return 'telephony_configs:list'


def get_tts_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for a TTS config"""
    return f'tts_config:{config_id}'


def get_tts_configs_list_cache_key() -> str:
    """Generate cache key for TTS configs list"""
    return 'tts_configs:list'


def get_stt_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for an STT config"""
    return f'stt_config:{config_id}'


def get_stt_configs_list_cache_key() -> str:
    """Generate cache key for STT configs list"""
    return 'stt_configs:list'


def get_voice_agent_cache_key(agent_id: UUID) -> str:
    """Generate cache key for a voice agent"""
    return f'voice_agent:{agent_id}'


def get_voice_agents_list_cache_key() -> str:
    """Generate cache key for voice agents list"""
    return 'voice_agents:list'


def get_welcome_message_url_cache_key(agent_id: UUID) -> str:
    """Generate cache key for a voice agent's welcome message presigned URL"""
    return f'voice_agent_welcome_url:{agent_id}'
