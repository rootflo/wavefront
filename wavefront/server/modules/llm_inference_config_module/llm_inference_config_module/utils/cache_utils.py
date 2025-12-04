"""Cache key generation utilities for LLM inference configurations"""

from uuid import UUID


def get_llm_inference_config_cache_key(config_id: UUID) -> str:
    """Generate cache key for an LLM inference config"""
    return f'llm_inference_config:{config_id}'


def get_llm_inference_configs_list_cache_key() -> str:
    """Generate cache key for LLM inference configs list"""
    return 'llm_inference_configs:list'
