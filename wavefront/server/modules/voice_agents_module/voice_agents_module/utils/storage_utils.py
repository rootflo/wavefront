"""
Storage utility functions for voice agents module.
"""

import uuid


def generate_welcome_message_key(voice_agent_id: uuid.UUID) -> str:
    """
    Generate cloud storage key for voice agent welcome message audio.

    Args:
        voice_agent_id: UUID of the voice agent

    Returns:
        str: Cloud storage key in format /voice_agents/{voice_agent_id}.mp3
    """
    return f'voice_agents/{voice_agent_id}.mp3'
