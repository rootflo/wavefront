"""Reading per-agent behaviour settings from ``voice_agent.conversation_config``.

The field is free-form JSON edited on the voice agent (Advanced tab). Each
behaviour reads its own section (``filler_speech``, ``turn_taking``); a bad value
is logged and replaced by the default so a typo never breaks a call.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping

from call_processing.log.logger import logger


def config_section(agent_config: Mapping[str, Any], name: str) -> Dict[str, Any]:
    """``conversation_config[name]`` as a dict ({} when absent or malformed)."""
    value = agent_config.get('conversation_config')
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    section = value.get(name) if isinstance(value, dict) else None
    return section if isinstance(section, dict) else {}


def bounded_number(
    section: Mapping[str, Any],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
    path: str,
) -> float:
    """``section[key]`` clamped to [minimum, maximum], or ``default`` if unusable."""
    if key not in section:
        return default
    value = section[key]
    if isinstance(value, bool):
        value = None  # true/false is not a number here
    try:
        number = float(value)
    except (TypeError, ValueError):
        logger.warning(f'Ignoring invalid {path}.{key}: {value!r}')
        return default
    return min(max(number, minimum), maximum)
